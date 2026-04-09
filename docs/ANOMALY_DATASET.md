# Anomaly Dataset Collection

Two labelled anomaly datasets built on the srsRAN 5G jBPF telemetry pipeline.

---

## Table of Contents

1. [Why Two Dataset Types?](#1-why-two-dataset-types)
2. [Stress Anomaly Dataset](#2-stress-anomaly-dataset)
3. [Realistic Channel Dataset](#3-realistic-channel-dataset)
4. [What jBPF Captures That E2SM-KPM Cannot](#4-what-jbpf-captures-that-e2sm-kpm-cannot)
5. [Reproduction](#5-reproduction)
6. [Dataset Structure and Data Quirks](#6-dataset-structure-and-data-quirks)

---

## 1. Why Two Dataset Types?

Real 5G gNBs fail in two qualitatively different ways:

| Failure class | Cause | Affected layer | Primary signals |
|---|---|---|---|
| **Channel anomaly** | RF impairments (fading, interference, mobility) | PHY → MAC → RLC cascade | SINR, MCS, HARQ failures, RLC delay |
| **Infrastructure anomaly** | OS/software stress (CPU contention, scheduler attacks, traffic floods) | gNB software stack | Hook latency, BSR |

Channel anomalies are visible on standard O-RAN E2SM-KPM metrics. Infrastructure anomalies are **not** — they require internal gNB telemetry. The two datasets together demonstrate both classes and show that they produce qualitatively different signatures.

---

## 2. Stress Anomaly Dataset

### 2.1 Overview

23 system-level scenarios applied to a live running pipeline. Each stressor targets a different component of the gNB software stack. Telemetry is collected for 90 seconds per scenario under a Rician fading baseline (K=3 dB, SNR=25 dB, Doppler=5 Hz).

**Script:** `scripts/stress_anomaly_collect.sh`  
**Primary dataset:** `stress_20260325_204950` (fading baseline)  
**Secondary dataset:** `stress_20260325_152810` (no-broker baseline, for comparison)

Baseline metrics (no stressor, fading channel):

| Metric | Value |
|---|---|
| FAPI-UL hook latency max | 70.7 µs |
| UL Buffer (BSR) max | 2095.9 KB |
| Mean SINR | 25.4 dB |
| Mean UL MCS | 27.9 |
| HARQ failures | 0 |

### 2.2 Scenarios and Results

#### CPU Stressors (01–06) — No anomaly

| ID | Label | FAPI-UL max | BSR max | SINR |
|----|-------|-------------|---------|------|
| 01 | cpu_pinned_50pct | 60.6 µs (0.86×) | 2128 KB (1.02×) | 25.3 dB |
| 02 | cpu_pinned_80pct | 37.2 µs (0.53×) | 2198 KB (1.05×) | 25.2 dB |
| 03 | cpu_pinned_95pct | 32.7 µs (0.46×) | 2343 KB (1.12×) | 25.0 dB |
| 04 | cpu_cpulimit_600 | 57.5 µs (0.81×) | 2079 KB (0.99×) | 25.3 dB |
| 05 | cpu_cpulimit_300 | 63.2 µs (0.89×) | 2035 KB (0.97×) | 25.1 dB |
| 06 | cpu_rt_preempt | 38.2 µs (0.54×) | 2438 KB (1.16×) | 24.7 dB |

**What this simulates:** A cloud-hosted gNB sharing a server with other workloads — noisy VM neighbours, runaway processes, CPU-heavy network functions.

**What happened:** Nothing. The gNB runs its scheduler threads at `SCHED_FIFO:96` (hard real-time priority). Normal-priority stress-ng workers cannot preempt RT threads regardless of load. Hook latency actually decreases slightly (likely cache warming). **These scenarios are not useful as anomaly training data** — a classifier cannot distinguish them from baseline.

**Key insight:** The 5G stack's real-time design deliberately protects it from ordinary CPU contention. Only attacks that directly modify scheduling policy have any effect.

---

#### Memory Pressure (07–10) — Weak to moderate

| ID | Label | FAPI-UL max | BSR max | SINR |
|----|-------|-------------|---------|------|
| 07 | mem_80pct_rss | 49.7 µs (0.70×) | 2549 KB (1.22×) | 24.7 dB |
| 08 | mem_60pct_rss | 76.8 µs (1.09×) | 2732 KB (1.30×) | 24.7 dB |
| 09 | mem_40pct_rss | 50.3 µs (0.71×) | 2812 KB (1.34×) | 24.6 dB |
| 10 | mem_40pct_balloon | 69.8 µs (0.99×) | **9570 KB (4.57×)** | 23.6 dB |

**What this simulates:** A gNB running low on available RAM — memory leak in another process, a large model loaded alongside the gNB, or an orchestrator that over-allocated the node.

**What happened:** Capping the gNB's RSS (07–09) produces only 1.2–1.3× BSR increase, within the range of mild GRC broker fading. The system-wide memory balloon (10) is more visible: BSR spikes 4.6× and SINR drops 1.8 dB as the OS evicts iperf3's socket buffers. Still not unique vs the channel broker.

---

#### Scheduler Attacks (11–14) — **Strong, unique**

| ID | Label | FAPI-UL max | BSR max | SINR |
|----|-------|-------------|---------|------|
| 11 | sched_rt_competitor_97 | 57.2 µs (0.81×) | 7043 KB (3.36×) | 23.7 dB |
| **12** | **sched_demote_rt_batch** | **7288.6 µs (103×)** | 6478 KB (3.09×) | 23.9 dB |
| **13** | **sched_demote_rt_other** | **3617.3 µs (51×)** | 7565 KB (3.61×) | 23.8 dB |
| **14** | **sched_demote_rt_plus_cpu** | **2911.3 µs (41×)** | 16050 KB (7.66×) | 23.4 dB |

**What this simulates:** A misconfiguration that changes the gNB's OS scheduling priority. In containerised deployments, an orchestrator sets thread priorities. A misconfigured deployment manifest, a privilege escalation, or a bug in the container runtime could accidentally demote the gNB's time-critical threads from real-time to normal scheduling class.

**What happened:** The most dramatic anomaly in the entire dataset. Demoting gNB threads from `SCHED_FIFO:96` to `SCHED_BATCH` caused the FAPI-UL hook latency to reach **7.3 ms — 103× above baseline**. The 5G MAC scheduler, FAPI layer, and L1 timing functions share the same real-time thread pool. When those threads are deprioritised, the scheduling loop stalls mid-slot, and the jBPF hook records the full stall duration.

Critically: **SINR stays at ~24 dB and MCS stays at ~28** — the radio link is unaffected. This is a pure software execution anomaly invisible to any radio channel measurement or E2SM-KPM metric.

---

#### Traffic Flooding (15–19) — **Strong BSR signal, unique**

| ID | Label | FAPI-UL max | BSR max | SINR | MCS |
|----|-------|-------------|---------|------|-----|
| **15** | **traffic_flood_100m** | 61.9 µs (0.88×) | **32129 KB (15.3×)** | 23.3 dB | 28.0 |
| **16** | **traffic_flood_150m** | 42.3 µs (0.60×) | **32813 KB (15.7×)** | 23.3 dB | 27.9 |
| **17** | **traffic_netem_delay** | 50.8 µs (0.72×) | **25977 KB (12.4×)** | 23.3 dB | 28.0 |
| 18 | traffic_burst_aggressive | 94.6 µs (1.34×) | **31445 KB (15.0×)** | 23.4 dB | 27.8 |
| **19** | **traffic_netem_burst** | 92.0 µs (1.30×) | **26458 KB (12.6×)** | 23.5 dB | 28.0 |

**What this simulates:** A misbehaving UE, a DDoS attack on the UE's application, or a burst of data that exceeds the uplink's physical capacity. More data arrives than the radio interface can carry.

**What happened:** BSR grows to 25–33 MB (12–16×) while SINR and MCS remain at maximum. The MAC scheduler correctly allocates all available PRBs every slot but cannot drain the queue faster than data arrives. **Zero HARQ failures.** This is the distinguishing signature: with the GRC broker, high BSR always accompanies SINR drop and MCS reduction. Here BSR spikes in complete isolation — a clean two-class separation.

---

#### Combined Stressors (20–22)

| ID | Label | FAPI-UL max | BSR max | SINR |
|----|-------|-------------|---------|------|
| 20 | combined_rt_preempt_traffic | 25.7 µs (0.36×) | **35547 KB (17.0×)** | 23.4 dB |
| 21 | combined_cpulimit_mem | 40.2 µs (0.57×) | 7944 KB (3.79×) | 24.2 dB |
| **22** | **combined_demote_traffic** | **2429.5 µs (34×)** | **38386 KB (18.3×)** | 23.3 dB |

**What this simulates:** Compound failures — the kind that actually bring networks down. Scenario 22 (RT demotion + 100 Mbps flood) is the most realistic: a scheduling misconfiguration at the same time as a traffic burst.

**What happened:** Scenario 22 produces a two-dimensional anomaly — hook latency 34× AND BSR 18× simultaneously. Single-cause faults only activate one anomaly axis. This distinction enables classifiers that not only flag anomalies but attribute root cause.

### 2.3 Anomaly Summary

| Scenario class | Hook anomaly | BSR anomaly | Unique vs GRC broker |
|---|---|---|---|
| CPU stressors (01–06) | None | None | **No** |
| Memory RSS (07–09) | None | Weak 1.2–1.3× | **No** |
| Memory balloon (10) | None | Moderate 4.6× | Partial |
| Sched RT competitor (11) | None | Moderate 3.4× | Partial |
| **Sched demote (12–14)** | **41–103×** | Moderate | **Yes** |
| **Traffic flood (15–19)** | None | **12–16×** | **Yes** |
| Combined preempt+traffic (20) | None | **17×** | **Yes** |
| Combined cpulimit+mem (21) | None | Moderate | No |
| **Combined demote+traffic (22)** | **34×** | **18×** | **Yes** |

**14 of 23 scenarios** produce anomaly signals not replicable with the GRC channel broker.

---

## 3. Realistic Channel Dataset

### 3.1 Overview

10 real-world-grounded channel scenarios collected sequentially. Each runs for 180 seconds with a full pipeline restart between scenarios. Produces a multi-schema labelled dataset across 4 scenario categories.

**Script:** `scripts/collect_channel_realistic.sh`  
**Exporter:** `scripts/export_channel_dataset.py`

> **Note on fading profiles:** EPA (7 taps) and EVA (9 taps) are LTE-era profiles from 3GPP TS 36.104 Table B.2, used because NR TDL/CDL profiles (TS 38.104) are not implemented in GNU Radio 3.10. They provide equivalent frequency-selective fading behaviour for single-cell ZMQ simulation.

### 3.2 Scenarios

| ID | Label | Category | Channel configuration |
|----|-------|----------|-----------------------|
| B1 | baseline_indoor_los | baseline | Rician K=6 dB, SNR=25 dB, fd=2 Hz |
| B2 | baseline_pedestrian_nlos | baseline | EPA-5, SNR=22 dB, fd=5 Hz |
| T1 | driveby_vehicular_epa | time_varying | EPA, SNR 20→12 dB (drive-by), fd 70→200 Hz, 25M load |
| T2 | driveby_epa_interference | time_varying | EPA, SNR=25 dB, drive-by + CW SIR=15 dB, 25M load |
| T3 | urban_walk_epa | time_varying | EPA, SNR=22 dB ±10 dB random walk, fd 1–20 Hz, 25M load |
| T4 | edge_of_cell_decline | time_varying | EPA, SNR 28→12 dB linear over 60s, 25M load |
| T5 | urban_walk_eva_canyon | time_varying | EVA, SNR=25 dB, random walk, fd=10 Hz, 20M load |
| S1 | cell_edge_cw_interference | steady_impairment | EPA, SNR=20 dB, CW SIR=15 dB, 2% drops, 20M load |
| S2 | rayleigh_deep_fade | steady_impairment | Rayleigh (K=−∞), SNR=28 dB, fd=5 Hz |
| S3 | high_speed_train_epa | steady_impairment | EPA, SNR=22 dB, fd=300 Hz, 3% drops, 20M load |
| L1 | rlf_cycle_clean_channel | rlf_cycle | Rician K=6 dB, SNR=25 dB, 4s blackout every 90s |
| L2 | rlf_cycle_degraded_epa | rlf_cycle | EPA, SNR=20 dB, fd=70 Hz, 4s blackout every 90s |

### 3.3 Expected signatures

The channel → MAC → RLC cascade is observable simultaneously across all layers at 1 ms resolution:

```
Channel SNR drops
  → PHY:  SINR drops at gNB receiver
  → MAC:  scheduler reduces MCS
  → MAC:  HARQ retransmissions increase
  → MAC:  throughput drops → UE buffer backs up → BSR grows
  → RLC:  SDU delay increases as queue depth grows
  → PDCP: delivered byte rate drops
```

| Scenario | MCS avg | HARQ | BSR | RLC delay max |
|---|---|---|---|---|
| B1 (clean LoS) | ~27.6 | None | ~1 MB steady | <40 ms |
| B2 (EPA NLoS) | ~15.7 | Moderate | ~1.7 MB | up to 1.8 s |
| S2 (Rayleigh) | ~27.6 | Bursty at fading nulls | ~1 MB | spikes at nulls |
| L1 (RLF cycle) | ~27.5 | Bursty on RLF | up to 13 MB at RLF | up to 4 s stall |
| T2 (drive-by+CW) | ~11.7 | Low | ~0 (ue crashed early) | minimal |

---

## 4. What jBPF Captures That E2SM-KPM Cannot

| Metric | jBPF schema | E2SM-KPM equivalent | Granularity |
|---|---|---|---|
| **Hook execution latency** | `jbpf_out_perf_list` | **None** | 1 ms |
| Per-UE MCS per slot | `harq_stats` | Approximate PM counter | 1 ms vs ≥10 ms |
| BSR per UE | `bsr_stats` | Not standardised | 1 ms |
| RLC SDU delay | `rlc_ul_stats`, `rlc_dl_stats` | Not exposed | 1 ms |
| RACH attempt events | `rach_stats` | `RRCConnEstabAtt` (count only) | Per event |
| RRC procedure outcomes | `rrc_ue_procedure` | Aggregate counters | Per event |
| HARQ process state | `harq_stats` | Aggregate BLER only | 1 ms |
| FAPI scheduling decisions | `dl_config_stats`, `ul_config_stats` | Not exposed | 1 ms |

E2SM-KPM minimum reporting period is 10 ms. jBPF captures state on every 1 ms slot boundary. Hook latency has no E2SM-KPM equivalent at all.

---

## 5. Reproduction

### Stress anomaly dataset

```bash
# Full 23-scenario run with Rician fading baseline (~49 min)
cat > /tmp/run_stress.sh << 'SCRIPT'
#!/usr/bin/env bash
exec bash ~/Desktop/stress_anomaly_collect.sh \
  --baseline "--fading --k-factor 3 --snr 25 --no-grafana" \
  --duration 90 --settle 25 --cooldown 10
SCRIPT
bash /tmp/run_stress.sh

# Generate 7 comparison plots
python3 scripts/plot_stress_comparison.py <dataset_dir>

# Generate 5 presentation figures
python3 project_extension/plot_bep_presentation.py <dataset_dir>
```

### Realistic channel dataset

```bash
# Full 10-scenario run (~37 min at 180s per scenario)
bash scripts/collect_channel_realistic.sh \
  --duration 180 --settle 60 --cooldown 15 \
  --output ~/channel_dataset

# Export to CSV + HDF5
python3 scripts/export_channel_dataset.py ~/channel_dataset

# Re-run only specific scenarios into an existing directory
bash scripts/collect_channel_realistic.sh \
  --scenarios T1,T4,L2 --duration 180 --settle 60 \
  --output ~/channel_dataset/existing_run
```

---

## 6. Dataset Structure and Data Quirks

### Stress anomaly

```
<run_dir>/
├── manifest.csv                    — scenario ID, label, category, status, duration
├── summary.txt                     — human-readable run report
├── baseline/  cpu/  memory/  sched/  traffic/  combined/
│   └── decoder_<ts>.log            — raw telemetry log per scenario
└── plots/
    ├── 01_hook_latency_bars.png
    ├── 02_bsr_comparison.png
    ├── 03_harq_sinr.png
    ├── 04_anomaly_heatmap.png
    ├── 05_timeseries_overlay.png
    ├── 06_multihook_bars.png
    └── 07_summary_dashboard.png
```

### Channel dataset

```
<run_dir>/
├── manifest.csv                    — scenario ID, label, flags, status, duration
├── summary.txt
├── channel_dataset.h5              — HDF5: /scenarios/<id>/<schema>
├── <ID>_<label>.log                — raw decoder log per scenario
└── csv/
    ├── crc_stats.csv               — HARQ failures, SINR, Tx counts
    ├── harq_stats.csv              — MCS per direction, retransmission counts
    ├── bsr_stats.csv               — UE buffer bytes (instantaneous)
    ├── uci_stats.csv               — CQI, SR, timing advance
    ├── rlc_ul_stats.csv / rlc_dl_stats.csv  — SDU delay, PDU bytes
    ├── ul_stats.csv / dl_stats.csv — PDCP bytes
    ├── jbpf_out_perf_list.csv      — hook latency p50/p90/p95/p99 per hook per slot
    ├── rach_stats.csv              — RACH attempt events
    ├── rrc_ue_procedure.csv        — RRC Setup / Reconfig / Reestablishment events
    └── ngap_procedure_*.csv        — NGAP InitialUEMessage, ContextSetup events
```

All CSV files share: `scenario_id`, `label`, `category`, `timestamp_utc`, `timestamp_unix`, `relative_s`.

### Cleaned feature matrices

Running `scripts/clean_datasets.py` merges all per-schema CSVs into two ML-ready files:

```
datasets/stress_anomaly/stress_features.csv     — 2892 rows × 49 columns, 23 scenarios
datasets/channel/channel_features.csv           — 2729 rows × 49 columns, 12 scenarios
```

```bash
python3 scripts/clean_datasets.py
```

Each file has one row per `(scenario_id, relative_s)` second with the following feature groups:

| Group | Columns | Source |
|---|---|---|
| Labels | `scenario_id`, `label`, `category`, `relative_s` | all schemas |
| BSR | `bsr_bytes`, `bsr_cnt`, `bsr_kb` | bsr_stats |
| SINR / HARQ | `crc_sinr_avg`, `crc_sinr_min`, `crc_sinr_max`, `crc_harq_fail`, `crc_tx`, `crc_succ_tx`, `harq_fail_rate`, `crc_success_rate` | crc_stats |
| MCS / retx | `harq_mcs_avg`, `harq_mcs_min`, `harq_mcs_max`, `harq_cons_retx`, `harq_slots_sampled` | harq_stats (both streams aggregated) |
| Hook latency | `hook_{p99,max,num}_us_<hook>` × 7 hooks | jbpf_out_perf_list |
| RLC UL | `rlc_bytes_per_s`, `rlc_pdu_bytes_per_s`, `rlc_lat_avg_us`, `rlc_lat_max_us`, `rlc_throughput_kb` | rlc_ul_stats (data bearer only) |

The 7 periodic hooks included: `fapi_ul_tti_request`, `fapi_dl_tti_request`, `rlc_ul_rx_pdu`, `rlc_ul_sdu_delivered`, `rlc_dl_tx_pdu`, `pdcp_ul_deliver_sdu`, `pdcp_ul_rx_data_pdu`.

RLC byte counters are differenced within each scenario (cumulative → per-second rate). The channel dataset has ~80 % NaN for non-hook columns because 5 of 12 scenarios are hook-only (UE never attached); `hook_p99_us_fapi_ul` and `hook_p99_us_fapi_dl` remain populated for all 12.

### Known data quirks

| Schema | Field | Issue | Handling |
|---|---|---|---|
| `harq_stats` | `retx_count` | Cumulative — never reset | Diff consecutive rows for per-window rate |
| `crc_stats` | `avg_sinr` | gNB-side post-equalisation SINR ≠ configured channel SNR | Use for relative comparison only |
| `uci_stats` | `ta_avg` | Sentinel overflow (1.7e16 ns) when TA unavailable | Filter `ta_avg > 1e12` |
| `crc_stats` | `duUeIndex=513` | Ghost HARQ entry — not a real UE | Filter `duUeIndex != 513` |
| `bsr_stats` | `bytes` | Serialised as string in protobuf | Cast with `int()` |
| All | `jbpf_out_perf_list` | Fires even with no UE attached | Use `num` field (TTI count) to detect idle periods |
