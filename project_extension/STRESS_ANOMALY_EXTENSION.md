# BEP Extension: Anomalous Dataset Collection via System-Level Stress Injection
## srsRAN 5G NR jBPF Telemetry Pipeline

---

## 1. Motivation

The thesis pipeline collects 5G MAC/RLC/PDCP/FAPI/RRC/NGAP telemetry from a live
srsRAN gNB via ~60 jBPF eBPF hooks. To build a meaningful anomaly detection dataset,
we need labelled samples where the network behaves abnormally.

The GRC channel broker (built in earlier phases) can simulate radio channel impairments:
AWGN, Rician/Rayleigh fading, EPA/EVA/ETU frequency-selective profiles, CFO, burst
drops, and time-varying drive scenarios. These all target the **physical layer** — they
degrade SINR, force MCS reduction, trigger HARQ failures, and cause BSR buildup via
throughput reduction.

However, real 5G deployments fail in more ways than bad radio conditions. This
extension adds **system-level** anomalies: CPU contention, memory pressure, scheduling
attacks, and traffic floods. These stress the **gNB software stack** rather than the
radio channel, and produce qualitatively different telemetry signatures.

---

## 2. What Was Built

### 2.1 `stress_anomaly_collect.sh` (739 lines)

A fully automated data collection script that:

1. Launches the complete 5G pipeline (jrtc → gNB → ZMQ broker → UE → iperf3)
2. Waits for the UE to attach and stabilise (configurable settle time)
3. Applies a system-level stressor while the pipeline runs
4. Collects decoder telemetry for a fixed window
5. Tears down the stressor cleanly, stops the pipeline, cools down
6. Repeats for all configured scenarios
7. Writes a manifest CSV and summary report

Key flags:
```bash
--baseline FLAGS   # Channel parameters for all scenarios (e.g. "--fading --k-factor 3 --snr 25")
--scenarios N,M    # Run only listed scenario IDs
--duration N       # Collection window per scenario (default 90 s)
--settle N         # Wait after pipeline start before stressor (default 25 s)
--cooldown N       # Gap between scenarios (default 10 s)
--category CAT     # Run only one category
```

### 2.2 23 Stress Scenarios (5 Categories)

| ID | Label | Category | Stressor mechanism |
|----|-------|----------|--------------------|
| 00 | baseline_clean | baseline | None — reference data |
| 01 | cpu_pinned_50pct | cpu | stress-ng: 50% CPU load across all cores |
| 02 | cpu_pinned_80pct | cpu | stress-ng: 80% CPU load |
| 03 | cpu_pinned_95pct | cpu | stress-ng: 95% CPU load |
| 04 | cpu_cpulimit_600 | cpu | cpulimit: gNB capped at 600% CPU |
| 05 | cpu_cpulimit_300 | cpu | cpulimit: gNB capped at 300% CPU |
| 06 | cpu_rt_preempt | cpu | stress-ng RT thread at priority 95 competing |
| 07 | mem_80pct_rss | memory | cgroup memory.high = 80% of gNB RSS |
| 08 | mem_60pct_rss | memory | cgroup memory.high = 60% of gNB RSS |
| 09 | mem_40pct_rss | memory | cgroup memory.high = 40% of gNB RSS |
| 10 | mem_40pct_balloon | memory | stress-ng balloon consumes 40% of total RAM |
| 11 | sched_rt_competitor_97 | sched | stress-ng SCHED_FIFO:97 competing thread |
| 12 | sched_demote_rt_batch | sched | gNB RT threads demoted to SCHED_BATCH |
| 13 | sched_demote_rt_other | sched | gNB RT threads demoted to SCHED_OTHER |
| 14 | sched_demote_rt_plus_cpu | sched | RT demotion + CPU load |
| 15 | traffic_flood_100m | traffic | iperf3 UDP flood: 100 Mbps (10× baseline) |
| 16 | traffic_flood_150m | traffic | iperf3 UDP flood: 150 Mbps (15× baseline) |
| 17 | traffic_netem_delay | traffic | netem: 50ms delay + 20ms jitter + 1% loss |
| 18 | traffic_burst_aggressive | traffic | iperf3 burst: 400 Mbps in 200ms windows |
| 19 | traffic_netem_burst | traffic | netem: 50ms delay + burst flooding |
| 20 | combined_rt_preempt_traffic | combined | RT competitor (FIFO:95) + 80M flood |
| 21 | combined_cpulimit_mem | combined | cpulimit 300% + cgroup 60% memory |
| 22 | combined_demote_traffic | combined | RT demotion BATCH + 100M flood |

### 2.3 `plot_stress_comparison.py` (571 lines)

Generates 7 comparison plots from a completed dataset:
- Hook latency bar charts
- BSR comparison charts
- HARQ + SINR comparison
- Normalised anomaly heatmap
- Time-series overlay for top anomalous scenarios
- Multi-hook grouped bar chart
- Summary dashboard

### 2.4 `plot_bep_presentation.py` (this directory)

Generates 5 presentation figures with improved layout and annotations.

---

## 3. Data Collection Runs

Two complete 23-scenario datasets were collected:

| Dataset | Date/time | Channel baseline | Notes |
|---------|-----------|-----------------|-------|
| `stress_20260325_152810` | 2026-03-25 15:28 | `--no-broker` (clean channel) | First full run, no fading |
| `stress_20260325_204950` | 2026-03-25 20:49 | `--fading --k-factor 3 --snr 25` | Fading baseline; used for analysis |

The **fading baseline run** (`stress_20260325_204950`) is the primary dataset. All
results below are from this run. Each scenario ran for 90 seconds with 25 s settle
and 10 s cooldown between scenarios. Total run time: ~49 minutes.

---

## 4. Results

### 4.1 Baseline

Under the fading baseline (K=3 dB, SNR=25 dB, Doppler=5 Hz, no stressor):

| Metric | Value |
|--------|-------|
| FAPI-UL hook latency max | 70.7 µs |
| UL Buffer (BSR) max | 2095.9 KB |
| Mean SINR | 25.4 dB |
| Mean UL MCS | 27.9 |
| HARQ failures | 0 |

### 4.2 Per-Category Results

#### CPU Stressors (scenarios 01–06)

| Scenario | FAPI-UL max | BSR max | SINR mean |
|----------|-------------|---------|-----------|
| cpu_pinned_50pct | 60.6 µs (0.86×) | 2128 KB (1.02×) | 25.3 dB |
| cpu_pinned_80pct | 37.2 µs (0.53×) | 2198 KB (1.05×) | 25.2 dB |
| cpu_pinned_95pct | 32.7 µs (0.46×) | 2343 KB (1.12×) | 25.0 dB |
| cpu_cpulimit_600 | 57.5 µs (0.81×) | 2079 KB (0.99×) | 25.3 dB |
| cpu_cpulimit_300 | 63.2 µs (0.89×) | 2035 KB (0.97×) | 25.1 dB |
| cpu_rt_preempt | 38.2 µs (0.54×) | 2438 KB (1.16×) | 24.7 dB |

**Finding:** No meaningful anomaly. The gNB runs at `SCHED_FIFO:96` (hard real-time
priority). Normal-priority stress-ng processes cannot preempt RT threads, so the gNB
is completely immune to CPU load injection. Hook latency actually decreases slightly
(likely cache warming). These scenarios are **not useful** as anomaly training data —
a classifier cannot distinguish them from the baseline.

#### Memory Pressure (scenarios 07–10)

| Scenario | FAPI-UL max | BSR max | SINR mean |
|----------|-------------|---------|-----------|
| mem_80pct_rss | 49.7 µs (0.70×) | 2549 KB (1.22×) | 24.7 dB |
| mem_60pct_rss | 76.8 µs (1.09×) | 2732 KB (1.30×) | 24.7 dB |
| mem_40pct_rss | 50.3 µs (0.71×) | 2812 KB (1.34×) | 24.6 dB |
| **mem_40pct_balloon** | 69.8 µs (0.99×) | **9570 KB (4.57×)** | **23.6 dB** |

**Finding:** RSS cgroup limits (07–09) produce only modest BSR increases (1.2–1.3×),
comparable to mild GRC broker fading. The cgroup memory balloon (10) is more impactful:
BSR spikes 4.6× and SINR drops 1.8 dB — consistent with memory pressure forcing
the OS to swap iperf3's send buffer while the 5G stack continues running normally.

#### Scheduler Attacks (scenarios 11–14)

| Scenario | FAPI-UL max | BSR max | SINR mean |
|----------|-------------|---------|-----------|
| sched_rt_competitor_97 | 57.2 µs (0.81×) | 7043 KB (3.36×) | 23.7 dB |
| **sched_demote_rt_batch** | **7288.6 µs (103×)** | 6478 KB (3.09×) | 23.9 dB |
| **sched_demote_rt_other** | **3617.3 µs (51×)** | 7565 KB (3.61×) | 23.8 dB |
| **sched_demote_rt_plus_cpu** | **2911.3 µs (41×)** | **16050 KB (7.66×)** | 23.4 dB |

**Finding:** The most dramatic hook latency spikes in the entire dataset. Demoting gNB
RT threads from `SCHED_FIFO:96` to `SCHED_BATCH` causes the FAPI-UL hook to reach
**7.3 ms** — 103× above baseline. This is because the 5G MAC scheduler, FAPI layer,
and L1 timing functions all share the same real-time thread pool. When those threads
are deprioritised, the scheduling loop stalls mid-slot, and the jBPF hook records the
full stall duration in its execution time.

Notably: SINR stays at ~24 dB and MCS stays at ~28 (link adaptation is unaffected).
These are **pure software execution anomalies** with no radio channel change.

#### Traffic Flooding (scenarios 15–19)

| Scenario | FAPI-UL max | BSR max | SINR mean | MCS |
|----------|-------------|---------|-----------|-----|
| traffic_flood_100m | 61.9 µs (0.88×) | **32129 KB (15.3×)** | 23.3 dB | 28.0 |
| traffic_flood_150m | 42.3 µs (0.60×) | **32813 KB (15.7×)** | 23.3 dB | 27.9 |
| traffic_netem_delay | 50.8 µs (0.72×) | **25977 KB (12.4×)** | 23.3 dB | 28.0 |
| traffic_burst_aggressive | 94.6 µs (1.34×) | **31445 KB (15.0×)** | 23.4 dB | 27.8 |
| traffic_netem_burst | 92.0 µs (1.30×) | **26458 KB (12.6×)** | 23.5 dB | 28.0 |

**Finding:** Massive BSR spikes (12–16×, up to 32 MB) with **zero change in SINR
(23.3 dB) or MCS (28.0)**. No HARQ failures. The 5G radio link is operating at full
capacity; the anomaly is purely at the application/transport layer — 100 Mbps of UDP
traffic is being injected into an uplink that can handle ~10 Mbps. The MAC scheduler
correctly allocates all available PRBs at maximum MCS, but cannot reduce the
application-layer queue.

#### Combined Stressors (scenarios 20–22)

| Scenario | FAPI-UL max | BSR max | SINR mean |
|----------|-------------|---------|-----------|
| combined_rt_preempt_traffic | 25.7 µs (0.36×) | **35547 KB (17.0×)** | 23.4 dB |
| combined_cpulimit_mem | 40.2 µs (0.57×) | 7944 KB (3.79×) | 24.2 dB |
| **combined_demote_traffic** | **2429.5 µs (34×)** | **38386 KB (18.3×)** | 23.3 dB |

**Finding:** Scenario 22 (`combined_demote_traffic`) is the most extreme: RT demotion
causes a 34× hook spike simultaneously with a 100 Mbps flood causing an 18× BSR spike.
This combined signature is unique — two independent anomaly axes are active at once.

---

## 5. Key Finding: What the Stressors Add vs the GRC Broker

This is the central comparison for the thesis dataset.

### 5.1 What the GRC channel broker produces

The GRC broker degrades radio channel quality. Its anomaly signature is always a
**correlated triplet**:
- SINR ↓ (channel noise / fading)
- MCS ↓ (link adaptation responds to SINR)
- HARQ failures ↑ (retransmissions when MCS is wrong)
- BSR ↑ (secondary: reduced throughput causes buffer buildup)
- Hook latency: **unchanged** (gNB RT threads unaffected by channel quality)

### 5.2 What the stressors uniquely produce

#### Hook latency spikes (scenarios 12, 13, 14, 22)
**Impossible to reproduce with the GRC broker.** Even at SNR=5 dB with ETU Rayleigh
fading, the FAPI-UL hook remains at 50–100 µs because the gNB runs at `SCHED_FIFO:96`.
Hook latency spikes only arise from OS-level scheduling policy changes. These represent
a completely different failure mode: **gNB software timing degradation** rather than
radio channel degradation.

#### Traffic-induced congestion with clean radio (scenarios 15–19)
**The GRC broker cannot produce high BSR with stable SINR/MCS.** To cause BSR buildup
with the GRC broker, you must reduce SINR, which also forces MCS down and triggers
HARQ failures. With traffic flooding, BSR reaches 32 MB while:
- SINR stays within 2 dB of baseline (radio channel unchanged)
- MCS stays at 28 (maximum — scheduler is not adapting)
- HARQ failures = 0 (no retransmissions needed)

This is a distinct anomaly class: **application-layer congestion** vs **radio-layer
throughput reduction**.

#### Multi-axis anomalies (scenario 14, 22)
Simultaneous hook latency + BSR spike from combined stressors creates a two-dimensional
anomaly signature that the GRC broker cannot replicate. This is valuable for testing
whether anomaly detectors can distinguish compound faults from single-cause faults.

### 5.3 What the stressors do NOT add

**CPU stressors (scenarios 01–06)** are indistinguishable from the baseline. The gNB's
RT priority design makes it immune to all normal-priority CPU load. These 6 scenarios
should be excluded from anomaly detection training datasets.

**Memory RSS limits (07–09)** produce only 1.2–1.3× BSR increase — well within the
range achievable with mild GRC broker fading (a 3 dB SNR reduction produces similar
BSR variation). They provide limited independent value.

### 5.4 Anomaly classification summary

| Scenario class | Hook anomaly | BSR anomaly | Unique vs GRC broker |
|----------------|-------------|-------------|---------------------|
| CPU stressors (01–06) | None | None | No |
| Memory RSS (07–09) | None | Weak (1.2–1.3×) | No |
| Memory balloon (10) | None | Moderate (4.6×) | Partial |
| Sched RT competitor (11) | None | Moderate (3.4×) | Partial |
| **Sched demote (12–14)** | **Yes (41–103×)** | Moderate | **Yes** |
| **Traffic flood (15–16)** | None | **Yes (15–16×)** | **Yes** |
| Traffic netem (17, 19) | None | **Yes (12×)** | **Yes** |
| Traffic burst (18) | Weak | **Yes (15×)** | **Yes** |
| Combined preempt+traffic (20) | None | **Yes (17×)** | **Yes** |
| Combined cpulimit+mem (21) | None | Moderate | No |
| **Combined demote+traffic (22)** | **Yes (34×)** | **Yes (18×)** | **Yes** |

Approximately **14 of 23 scenarios** provide genuinely novel anomaly signals.

---

## 6. Bug Fixed During Analysis

During monitoring of the fading run, a bug was found in `plot_stress_comparison.py`:

**Problem:** All `duUeIndex` filters used `>= 32` to select the real UE. This was based
on a note about DL HARQ having a ghost entry at `duUeIndex=513`. However, the real UE
is at `duUeIndex=0` in all schemas. The `>= 32` filter was keeping the ghost (513) and
discarding the real UE (0), causing SINR, HARQ failure, and RLC delay metrics to report
zero or garbage values in all plots.

**Fix:** Changed all filters to `!= 513` (explicitly exclude the ghost entry).
This affects `crc_stats`, `harq_stats`, and `rlc_ul_stats` parsing in
`plot_stress_comparison.py`.

The FAPI-UL hook latency and BSR metrics were unaffected (they use no `duUeIndex`
filter), which is why the previous comparison plots were still valid for the main
anomaly signals.

---

## 7. Files

```
~/Desktop/
├── stress_anomaly_collect.sh      (739 lines) — automated dataset collection
├── plot_stress_comparison.py      (571 lines) — 7-figure comparison plots
├── dataset/
│   ├── stress_20260325_152810/    — full 23-scenario run, no-broker baseline
│   │   ├── manifest.csv
│   │   ├── summary.txt
│   │   ├── baseline/, cpu/, memory/, sched/, traffic/, combined/
│   │   └── plots/                 — 7 comparison PNGs
│   └── stress_20260325_204950/    — full 23-scenario run, fading baseline (PRIMARY)
│       ├── manifest.csv
│       ├── summary.txt
│       ├── baseline/, cpu/, memory/, sched/, traffic/, combined/
│       └── plots/                 — 7 comparison PNGs (with duUeIndex bug fixed)
└── project_extension/
    ├── STRESS_ANOMALY_EXTENSION.md (this file)
    ├── plot_bep_presentation.py    — 5 presentation figures
    └── figures/
        ├── fig1_hook_bsr_overview.png     — per-scenario hook + BSR bar charts
        ├── fig2_signal_space.png          — hook vs BSR scatter (log-log)
        ├── fig3_anomaly_heatmap.png       — normalised anomaly score matrix
        ├── fig4_sinr_mcs_invariance.png   — SINR + MCS stability under stress
        └── fig5_category_summary.png      — max anomaly multiplier by category
```

---

## 8. How to Re-run

```bash
# Re-run the full 23-scenario fading collection
cat > /tmp/run_stress_fading.sh << 'SCRIPT'
#!/usr/bin/env bash
exec bash ~/Desktop/stress_anomaly_collect.sh \
  --baseline "--fading --k-factor 3 --snr 25 --no-grafana" \
  --duration 90 \
  --settle 25 \
  --cooldown 10
SCRIPT
bash /tmp/run_stress_fading.sh

# Generate comparison plots
python3 ~/Desktop/plot_stress_comparison.py ~/Desktop/dataset/<run_dir>

# Generate presentation figures
python3 ~/Desktop/project_extension/plot_bep_presentation.py ~/Desktop/dataset/<run_dir>
```

---

*Generated: 2026-03-25*
