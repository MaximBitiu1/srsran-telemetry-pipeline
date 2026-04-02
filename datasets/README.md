# Datasets

Two labelled anomaly datasets exported from the srsRAN 5G NR jBPF telemetry pipeline.
Raw logs are stored locally at `~/Desktop/datasets/` (stress_anomaly/ and channel/).

---

## Directory Layout

```
datasets/
├── stress_anomaly/
│   ├── csv/                  ← 6 schema CSV files, ~37 K rows, 23 scenarios
│   └── plots/                ← 23 per-scenario + 8 summary plots
└── channel/
    ├── csv/                  ← 17 schema CSV files, ~14 K rows, 12 scenarios
    └── plots/                ← 12 per-scenario + overview + summary plots
```

---

## Dataset 1 — Stress Anomaly (`stress_anomaly/`)

**Collected:** 2026-03-25  
**Raw logs:** `~/Desktop/datasets/stress_anomaly/`  
**Script:** `scripts/stress_anomaly_collect.sh`  
**Scenarios:** 23  
**Channel baseline:** Rician fading K=3 dB, SNR=25 dB, fd=5 Hz (C broker)  
**Per-scenario collection:** 25 s settle · 180 s capture · 10 s cooldown

### Scenarios

| ID | Label | Category | Stressor |
|----|-------|----------|---------|
| 00 | baseline_clean | baseline | No stressor — Rician fading only |
| 01 | cpu_pinned_50pct | cpu | stress-ng at 50% CPU, pinned to gNB NUMA node |
| 02 | cpu_pinned_80pct | cpu | stress-ng at 80% CPU, pinned |
| 03 | cpu_pinned_95pct | cpu | stress-ng at 95% CPU, pinned — near-total saturation |
| 04 | cpu_cpulimit_600 | cpu | cpulimit cap on gNB process: 600% (6 cores) |
| 05 | cpu_cpulimit_300 | cpu | cpulimit cap on gNB process: 300% (3 cores) |
| 06 | cpu_rt_preempt | cpu | SCHED_FIFO:50 competitor thread (below gNB at :96) |
| 07 | mem_80pct_rss | memory | Balloon gNB RSS to 80% of physical RAM |
| 08 | mem_60pct_rss | memory | Balloon gNB RSS to 60% of physical RAM |
| 09 | mem_40pct_rss | memory | Balloon gNB RSS to 40% of physical RAM |
| 10 | mem_40pct_balloon | memory | System-wide memory balloon (evicts all process pages) |
| 11 | sched_rt_competitor_97 | sched | SCHED_FIFO:97 thread above gNB — regularly yields |
| 12 | sched_demote_rt_batch | sched | Demote gNB threads from SCHED_FIFO:96 → SCHED_BATCH |
| 13 | sched_demote_rt_other | sched | Demote gNB threads from SCHED_FIFO:96 → SCHED_OTHER |
| 14 | sched_demote_rt_plus_cpu | sched | SCHED_OTHER demotion + 80% CPU load |
| 15 | traffic_flood_100m | traffic | 100 Mbps iperf3 UDP flood on UL interface |
| 16 | traffic_flood_150m | traffic | 150 Mbps iperf3 UDP flood — saturates radio link completely |
| 17 | traffic_netem_delay | traffic | tc netem: 20 ms delay + 50 Mbps cross-traffic |
| 18 | traffic_burst_aggressive | traffic | 8 × 1 Gbps UDP bursts (50 ms each, 5 s apart) |
| 19 | traffic_netem_burst | traffic | Periodic tc netem bursts with correlated loss + delay |
| 20 | combined_rt_preempt_traffic | combined | SCHED_FIFO:97 competitor + 100 Mbps flood |
| 21 | combined_cpulimit_mem | combined | cpulimit 300% + system-wide memory balloon |
| 22 | combined_demote_traffic | combined | SCHED_BATCH demotion + 100 Mbps flood |

### CSV Schema Reference

Every CSV has these metadata columns on every row:

| Column | Type | Description |
|--------|------|-------------|
| `scenario_id` | int (0–22) | Scenario index |
| `label` | string | Scenario name (e.g. `sched_demote_rt_batch`) |
| `category` | string | One of: baseline, cpu, memory, sched, traffic, combined |
| `timestamp_utc` | ISO-8601 | Wall-clock timestamp of the telemetry record |
| `timestamp_unix` | float | Unix epoch seconds |
| `relative_s` | float | Seconds since scenario collection start |

#### `harq_stats.csv` — 5 326 rows · 15 columns
MAC-layer HARQ state and MCS per 1 ms slot.

| Column | Description |
|--------|-------------|
| `avg_mcs` | Average DL MCS assigned to this UE in this slot (0–28) |
| `mcs_min` / `mcs_max` | Per-slot MCS range |
| `mcs_count` | Number of MCS samples aggregated |
| `cons_retx_max` | Maximum consecutive HARQ retransmissions |
| `max_nof_harq_retxs` | Configured maximum HARQ retransmissions |
| `cell_id` | Serving cell ID |
| `duUeIndex` | UE index within the DU |
| `stream_id` | HARQ stream (0/1 for MIMO) |

#### `crc_stats.csv` — 2 662 rows · 15 columns
PHY-layer CRC outcomes and UL SINR per slot.

| Column | Description |
|--------|-------------|
| `avg_sinr` | Average UL SINR (dB) over slot |
| `min_sinr` / `max_sinr` | Per-slot SINR range |
| `cnt_sinr` | Number of SINR samples |
| `cnt_tx` | Total transmissions attempted |
| `succ_tx` | Successful (CRC-passing) transmissions |
| `harq_failure` | Number of HARQ failures in slot |
| `cons_max` | Maximum consecutive CRC failures |
| `duUeIndex` | UE index |

#### `bsr_stats.csv` — 2 662 rows · 9 columns
UE uplink buffer occupancy (Buffer Status Report).

| Column | Description |
|--------|-------------|
| `bytes` | UL buffer bytes queued at the UE |
| `cnt` | Number of BSR reports aggregated in this slot |
| `duUeIndex` | UE index |

#### `jbpf_out_perf_list.csv` — 21 238 rows · 12 columns
Per-hook eBPF execution latency for all ~57 active jBPF codelets. **Novel metric — no E2SM-KPM equivalent.**

| Column | Description |
|--------|-------------|
| `hook_name` | eBPF codelet name (e.g. `fapi_ul_tti_request`, `fapi_dl_tti_request`) |
| `p50_us` | Median hook execution latency (µs) |
| `p90_us` | 90th percentile latency (µs) |
| `p99_us` | 99th percentile latency (µs) — primary anomaly signal |
| `max_us` | Maximum latency in reporting window (µs) |
| `num` | Number of hook invocations in reporting window |

Baseline p99 ≈ 0.8–70 µs. Under SCHED_BATCH demotion: up to **7 289 µs (103×)**.

#### `rlc_ul_stats.csv` — 2 885 rows · 14 columns
RLC uplink SDU delivery latency and byte counts.

| Column | Description |
|--------|-------------|
| `sdu_delivered_lat_avg_us` | Average RLC SDU delivery latency (µs) |
| `sdu_delivered_lat_max_us` | Maximum RLC SDU delivery latency (µs) |
| `sdu_delivered_lat_count` | Number of SDUs delivered |
| `sdu_delivered_bytes_total` | Cumulative bytes delivered (counter — diff consecutive rows) |
| `pdu_bytes_total` | Cumulative PDU bytes (counter) |
| `rb_id` | Radio Bearer ID |
| `is_srb` | 1 = Signalling RB, 0 = Data RB |
| `duUeIndex` | UE index |

#### `uci_stats.csv` — 2 676 rows · 13 columns
UCI (Uplink Control Information) feedback counters — HARQ-ACK and CQI reports.

---

## Dataset 2 — Realistic Channel (`channel/`)

**Collected:** 2026-04-01 (B1, B2, T2, S2, L1) and 2026-04-02 (T1, T3, T4, T5, S1, S3, L2)  
**Raw logs:** `~/Desktop/datasets/channel/`  
**Script:** `scripts/collect_channel_realistic.sh`  
**Scenarios:** 12 (7 with full MAC data · 5 with hook-latency only)  
**Broker:** GRC Python broker (`srsran_channel_broker.py`) — EPA/EVA frequency-selective fading  
**UL channel:** Flat Rician K=6, SNR=25 dB (kept constant to prevent PUCCH deep fade)  
**Per-scenario collection:** 60 s settle · 180 s capture · 15 s cooldown

### Scenarios

| ID | Label | Category | Channel configuration | MAC data |
|----|-------|----------|-----------------------|----------|
| B1 | baseline_indoor_los | baseline | Rician K=6 dB, SNR=25 dB, fd=2 Hz | Yes |
| B2 | baseline_pedestrian_nlos | baseline | EPA, SNR=22 dB, fd=5 Hz | Yes |
| T1 | driveby_vehicular_epa | time_varying | EPA, SNR 20→12 dB, fd 70→200 Hz, 25 Mbps | Yes (81 s) |
| T2 | driveby_epa_interference | time_varying | EPA, SNR=25 dB, CW SIR=15 dB, 25 Mbps | Yes (UE crash) |
| T3 | urban_walk_epa | time_varying | EPA, SNR=22±10 dB random walk, fd 1–20 Hz | Hook only |
| T4 | edge_of_cell_decline | time_varying | EPA, SNR 28→12 dB linear over 60 s | Hook only |
| T5 | urban_walk_eva_canyon | time_varying | EVA, SNR=25 dB, fd=10 Hz | Hook only |
| S1 | cell_edge_cw_interference | steady_impairment | EPA, SNR=20 dB, CW SIR=15 dB, 20 Mbps | Yes (25 s) |
| S2 | rayleigh_deep_fade | steady_impairment | Rayleigh (K=−∞), SNR=28 dB, fd=5 Hz | Yes |
| S3 | high_speed_train_epa | steady_impairment | EPA, SNR=22 dB, fd=300 Hz, 3% drops | Hook only |
| L1 | rlf_cycle_clean_channel | rlf_cycle | Rician K=6, SNR=25 dB, 4 s blackout/90 s | Yes |
| L2 | rlf_cycle_degraded_epa | rlf_cycle | EPA, SNR=20 dB, fd=70 Hz, 4 s blackout/90 s | Hook only |

### Key Results

| Scenario | MCS avg | BSR max (MB) | RLC delay max (ms) | HARQ fail/s |
|----------|---------|--------------|-------------------|-------------|
| B1 | 27.6 | 1.99 | 37 | 0.00 |
| B2 | 15.7 | 6.53 | 1853 | 4.14 |
| T1 | 11.6 | 61.6 | 1229 | 1.02 |
| T2 | 12.0 | 0.004 | 13 | 0.64 |
| S1 | 22.0 | 37.6 | 1856 | 2.93 |
| S2 | 27.6 | 2.01 | 43 | 0.00 |
| L1 | 27.5 | 12.95 | 4072 | 1.46 |

### CSV Schema Reference

The channel dataset contains all 6 schemas from the stress dataset plus 11 additional event-based schemas that are only populated for scenarios where the UE successfully attached and maintained connection.

#### Core schemas (same columns as stress dataset)

`harq_stats.csv` · `crc_stats.csv` · `bsr_stats.csv` · `jbpf_out_perf_list.csv` · `rlc_ul_stats.csv` · `uci_stats.csv`

> **Note on UL SINR:** `crc_stats.avg_sinr` reflects only the UL channel (kept flat-Rician). It does **not** reflect DL channel impairment. Use `harq_stats.avg_mcs` as the DL quality proxy.

> **Note on cumulative counters:** `rlc_ul_stats.sdu_delivered_bytes_total` and `pdu_bytes_total` are hardware-style monotonic counters — diff consecutive rows within the same scenario to get per-interval bytes.

#### `rlc_dl_stats.csv` — 115 rows · 11 columns
RLC downlink delivery statistics (DL bearer throughput and latency).

| Column | Description |
|--------|-------------|
| `sdu_delivered_lat_avg_us` | Average DL RLC SDU delivery latency (µs) |
| `sdu_delivered_lat_max_us` | Maximum DL RLC SDU delivery latency (µs) |
| `sdu_delivered_bytes_total` | Cumulative DL bytes delivered (counter) |
| `pdu_bytes_total` | Cumulative DL PDU bytes (counter) |
| `rb_id` | Radio Bearer ID |
| `is_srb` | 1 = Signalling RB |

#### `dl_config_stats.csv` — 109 rows · 19 columns
FAPI DL_TTI.request scheduling decisions — what the MAC scheduler allocated per slot.

| Column | Description |
|--------|-------------|
| `dl_pdsch_bytes` | DL PDSCH bytes scheduled in slot |
| `dl_pdsch_prbs` | Number of PRBs allocated for DL |
| `dl_nof_pdsch_allocs` | Number of PDSCH allocations |
| `dl_nof_dl_symb` | DL symbols in slot |
| `pdcch_nof_allocs` | Number of PDCCH allocations |

#### `ul_config_stats.csv` — 107 rows · 18 columns
FAPI UL_TTI.request scheduling decisions — UL grants issued per slot.

| Column | Description |
|--------|-------------|
| `ul_pusch_bytes` | UL PUSCH bytes scheduled |
| `ul_pusch_prbs` | PRBs allocated for UL |
| `ul_nof_pusch_allocs` | Number of PUSCH allocations |
| `ul_nof_ul_symb` | UL symbols in slot |

#### `dl_stats.csv` / `ul_stats.csv` — ~90–113 rows
Aggregate DL/UL throughput counters per reporting interval.

| Column | Description |
|--------|-------------|
| `dl_bytes` / `ul_bytes` | Bytes transferred in interval |
| `dl_pdus` / `ul_pdus` | PDU count |

#### `rach_stats.csv` — 3 rows · 8 columns
RACH preamble detection events (one row per RACH attempt).

| Column | Description |
|--------|-------------|
| `preamble_id` | RACH preamble index |
| `ta_ns` | Timing advance estimate (ns) |
| `snr_db` | Measured preamble SNR |
| `cell_id` | Serving cell |

#### `rrc_ue_procedure.csv` — 6 rows · 10 columns
RRC connection procedure outcomes (one row per RRC event).

| Column | Description |
|--------|-------------|
| `procedure` | Procedure name (e.g. `rrc_setup`, `rrc_reconfig`) |
| `cause` | Trigger cause |
| `result` | success / failure |
| `duUeIndex` | UE index |

#### `rrc_ue_add.csv` / `rrc_ue_remove.csv`
UE context creation/deletion events. One row per UE attach/detach.

#### `ngap_procedure_started.csv` / `ngap_procedure_completed.csv`
NG-AP (N2) procedure events between gNB and AMF (InitialUEMessage, UEContextSetup, etc.).

---

## Anomaly Classes Summary

| Class | Primary signal | Scenarios | GRC-replicable? |
|-------|---------------|-----------|-----------------|
| Scheduler-induced hook spike | `jbpf_out_perf_list.p99_us` 40–103× | 12, 13, 14, 22 | No |
| Traffic-induced BSR spike | `bsr_stats.bytes` 12–16× | 15–19, 20, 22 | No |
| Channel-induced cascade | MCS ↓ + BSR ↑ + RLC delay ↑ + HARQ fail ↑ | B2, T1, S1, L1 | Yes |
| Baseline / clean | All metrics nominal | 00, B1, S2 | — |

---

## Loading the Data

```python
import pandas as pd
from pathlib import Path

REPO = Path("~/Desktop/srsran-telemetry-pipeline").expanduser()

# Load stress dataset — all scenarios
harq  = pd.read_csv(REPO / "datasets/stress_anomaly/csv/harq_stats.csv")
bsr   = pd.read_csv(REPO / "datasets/stress_anomaly/csv/bsr_stats.csv")
perf  = pd.read_csv(REPO / "datasets/stress_anomaly/csv/jbpf_out_perf_list.csv")
crc   = pd.read_csv(REPO / "datasets/stress_anomaly/csv/crc_stats.csv")
rlc   = pd.read_csv(REPO / "datasets/stress_anomaly/csv/rlc_ul_stats.csv")

# Filter to a single scenario
sched_demote = harq[harq["label"] == "sched_demote_rt_batch"]

# Load channel dataset
ch_harq = pd.read_csv(REPO / "datasets/channel/csv/harq_stats.csv")
ch_perf = pd.read_csv(REPO / "datasets/channel/csv/jbpf_out_perf_list.csv")

# FAPI-UL hook latency for channel scenarios
fapi_ul = ch_perf[ch_perf["hook_name"] == "fapi_ul_tti_request"]
```

---

For full methodology, per-scenario explanations, and result analysis see:
- [`docs/ANOMALY_COLLECTION_REPORT.md`](../docs/ANOMALY_COLLECTION_REPORT.md)
- [`docs/ANOMALY_DATASET.md`](../docs/ANOMALY_DATASET.md)
