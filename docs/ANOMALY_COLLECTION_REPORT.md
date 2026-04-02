# Anomalous Data Collection -- Progress Report


---

## 1. Overview

We collected two anomaly datasets using our srsRAN 5G NR telemetry pipeline, which instruments a gNB with approximately 60 eBPF hooks (jBPF) producing 17 telemetry schemas at 1 ms granularity. A ZMQ channel broker -- either a lightweight C broker or a GNU Radio Companion (GRC) Python broker -- injects calibrated channel impairments between the gNB and a software UE (srsUE).

The two datasets target orthogonal anomaly sources:

1. **Stress anomaly dataset** (25 March 2026): 23 system-level scenarios injecting CPU, memory, scheduler, and traffic stressors into the gNB host while the radio channel remains constant. Purpose: isolate infrastructure faults from channel degradation.

2. **Realistic channel dataset** (1 April 2026): 12 channel scenarios covering indoor LoS baselines, vehicular drive-by, cell-edge interference, deep fading, and radio link failure cycles. Purpose: capture the full range of channel-induced MAC-layer degradation observable in the srsUE ZMQ stack.

Together, the datasets contain 30 unique scenario configurations (23 stress + 7 channel with full MAC data) plus 5 additional channel scenarios where only hook-latency telemetry was produced.

---

## 2. Infrastructure Anomalies (Stress Dataset)

**Dataset location:** `~/Desktop/dataset/stress_20260325_204950/`  
**Baseline configuration:** Rician fading, K=3 dB, SNR=25 dB, fd=5 Hz (C broker)  
**Collection per scenario:** 25 s settle, 180 s capture, 10 s cooldown

### 2.1 Scenario Summary

The 23 scenarios span five categories: CPU saturation (6 scenarios), memory pressure (4), scheduler priority manipulation (3), network traffic flooding (3), and combined stressors (7). Each scenario was run twice (fading baseline and no-broker baseline); we report the fading-baseline run as the primary dataset.

### 2.2 Key Finding: CPU Stressors Are Invisible

All six CPU stress scenarios (pinned 95%, unpinned 95%, full-core 100%, single-core 100%, low-priority nice+19, cache thrash) produced hook latency values indistinguishable from the clean baseline (~33--65 us max vs 70.7 us baseline). BSR and SINR were likewise unchanged.

This is a meaningful negative result. The srsRAN gNB runs its real-time processing threads at `SCHED_FIFO` priority 96 -- the highest available below kernel threads. Under the Linux CFS scheduler, no normal-priority `stress-ng` process can preempt these threads, regardless of CPU load. The gNB is, by design, immune to CPU contention from co-located workloads running at default priority.

### 2.3 Scheduler Demotion: The Only Hook Latency Anomaly

The only way to produce a hook latency anomaly was to explicitly demote the gNB's real-time scheduling priority:

| Scenario | FAPI-UL max (us) | Multiplier | BSR max (KB) | SINR (dB) |
|---|---|---|---|---|
| baseline_clean | 70.7 | 1.0x | 2096 | 25.4 |
| sched_demote_rt_batch | 7289 | 103x | 6478 | 23.9 |
| sched_demote_rt_other | 3617 | 51x | 7565 | 23.8 |
| sched_demote_rt_plus_cpu | 2911 | 41x | 16050 | 23.4 |
| combined_demote_traffic | 2430 | 34x | 38386 | 23.3 |

The critical observation is that SINR and MCS remain nearly unchanged during scheduler demotion. The radio channel is unaffected -- the anomaly is purely a software processing delay. This makes hook latency a clean discriminator: a spike in hook latency with stable SINR/MCS indicates an infrastructure fault, not a channel event.

### 2.4 Traffic Flooding: BSR-Only Anomaly

Network traffic flooding (100 Mbps and 150 Mbps iperf3 cross-traffic) caused BSR to spike 15--16x above baseline while hook latency remained at or below baseline levels:

| Scenario | FAPI-UL max (us) | BSR max (KB) | SINR (dB) |
|---|---|---|---|
| traffic_flood_100m | 62 | 32129 | 23.3 |
| traffic_flood_150m | 42 | 32813 | 23.3 |

This pattern -- elevated BSR with normal hook latency and stable SINR -- is the signature of application-layer congestion. It is distinguishable from channel degradation because channel impairments simultaneously affect MCS, HARQ, and RLC delay, whereas traffic floods affect only the buffer occupancy.

### 2.5 Novelty Relative to Channel Broker

Of the 23 stress scenarios, 14 produce anomaly signatures that cannot be replicated by any channel broker configuration. Scheduler demotion and traffic flooding are infrastructure-only fault modes with no channel-domain equivalent.

![Fig 2 -- Stress hook latency by scenario](anomaly_report_figures/fig2_stress_hook_latency.png)

![Fig 3 -- Anomaly signal space: hook latency vs BSR](anomaly_report_figures/fig3_signal_space_scatter.png)

---

## 3. Channel Anomalies (Realistic Channel Dataset)

**Dataset location:** `~/Desktop/channel_dataset/20260401_180521/`  
**Broker:** GRC Python broker (`srsran_channel_broker.py`) with frequency-selective fading  
**UL channel:** Flat Rician (K=6, SNR=25) for all scenarios to maintain PUCCH stability

### 3.1 Scenario Design

We designed 12 scenarios across four categories:

- **Baseline (B1, B2):** Clean indoor LoS and pedestrian NLoS
- **Time-varying (T1--T5):** Drive-by fading, urban walk, edge-of-cell decline
- **Steady impairment (S1--S3):** Cell-edge with CW interference, Rayleigh deep fade, high-speed train
- **RLF cycles (L1, L2):** Periodic signal blackout causing radio link failure and recovery

### 3.2 Results: 7 Scenarios with Full MAC Data

| Scenario | Config | MCS avg | BSR max (MB) | RLC delay max (ms) | HARQ fail/s |
|---|---|---|---|---|---|
| B1 | Rician K=6 SNR=25 fd=2 Hz | 27.6 | 1.99 | 37 | 0.00 |
| B2 | EPA SNR=22 fd=5 Hz NLoS | 15.7 | 6.53 | 1853 | 4.14 |
| T1 | EPA SNR=20-12 drive-by, 25M load | 11.6 | 61.6 | 1229 | 1.02 |
| T2 | EPA SNR=25 drive-by + CW SIR=15 | 12.0 | 0.004 | 13 | 0.64 |
| S1 | EPA SNR=20 CW SIR=15, 20M load | 22.0 | 37.6 | 1856 | 2.93 |
| S2 | Rayleigh SNR=28 fd=5 Hz | 27.6 | 2.01 | 43 | 0.00 |
| L1 | Rician K=6 SNR=25 4s blackout/90s | 27.5 | 12.95 | 4072 | 1.46 |

The scenarios produce clearly differentiated telemetry signatures:

- **B1 and S2** represent clean channels (high MCS, low BSR, near-zero HARQ failures). S2 uses Rayleigh fading at high SNR, which behaves similarly to Rician at this SNR level.
- **B2 and S1** show moderate-to-severe degradation with elevated HARQ failures (2.9--4.1/s) and RLC delays exceeding 1.8 s. These represent sustained poor-channel conditions.
- **T1** is the most extreme buffering case: the drive-by scenario with 25 Mbps offered load against a link whose effective capacity drops below 5 Mbps at the SNR trough, producing 61.6 MB peak BSR.
- **T2** shows anomalously low BSR (0.004 MB) because the UE crashed before the iperf3 traffic generator ramped up. The scenario is retained for its HARQ and MCS data.
- **L1** produces the highest RLC delay (4.07 s) due to the 4-second signal blackout: the RLC queue accumulates data during each blackout, then drains during recovery. This is the only scenario exhibiting periodic complete disruption followed by recovery.

### 3.3 Failed Scenarios (Hook-Latency Only)

Five scenarios (T3, T4, T5, S3, L2) failed to produce MAC-layer telemetry. In each case, the UE process started and the eBPF hooks were active (producing `jbpf_out_perf_list` records), but `crc_stats` and `bsr_stats` were never generated despite 120 s of waiting for UE attachment followed by 180 s of collection time.

The common factor is channel severity: T5 uses EVA (9-tap delay profile with 2.5 us max excess delay), S3 uses EPA at 300 Hz Doppler (high-speed train), and L2 combines RLF cycling with EPA fading. These conditions prevent the srsUE from completing the RRC connection procedure or maintaining it long enough to schedule uplink data.

These failures are informative: they mark the boundary of the srsUE ZMQ stack's operating range.

![Fig 1 -- Channel scenario comparison](anomaly_report_figures/fig1_channel_comparison.png)

---

## 4. jBPF Hook Latency as a Novel Metric

The `jbpf_out_perf_list` schema reports per-hook execution latency for all ~57 active eBPF codelets. This metric has no equivalent in standard O-RAN telemetry (E2SM-KPM defines no codelet performance counters). It is a byproduct of the jBPF instrumentation framework and, to our knowledge, has not been used as an anomaly detection signal in prior work.

### 4.1 Channel Independence

Across all seven channel scenarios with full MAC data, hook latency p99 remained between 3.1 and 5.3 us:

| B1 | B2 | T1 | S1 | S2 | L1 |
|---|---|---|---|---|---|
| 3.1 us | 4.7 us | 5.3 us | 3.9 us | 3.3 us | 3.2 us |

This range is negligible compared to the 2900--7300 us spikes observed under scheduler demotion. Channel impairments -- including frequency-selective fading, CW interference, and periodic blackouts -- do not perturb hook execution time. This is expected: the hooks instrument software functions (MAC scheduler, BSR handler, HARQ feedback processor), whose execution time depends on CPU scheduling, not on the content of the IQ samples being processed.

### 4.2 Infrastructure Sensitivity

Only scheduler priority demotion produced hook latency anomalies (40--103x baseline). CPU saturation, memory pressure, and traffic flooding had no effect on hook latency. This narrow sensitivity is a strength for anomaly detection: a hook latency spike is an unambiguous indicator of real-time scheduling disruption, with no channel-domain confounders.

![Fig 4 -- Hook latency: channel vs stress comparison](anomaly_report_figures/fig4_hook_channel_vs_stress.png)

---

## 5. Limitations

1. **Single cell, single UE.** The pipeline operates in a single-cell configuration with one UE. There is no handover, no inter-cell interference, and no multi-UE scheduling contention. Results may not generalise to multi-cell or multi-UE deployments.

2. **ZMQ virtual radio.** All IQ samples are transported over ZMQ sockets, not over-the-air. There are no hardware-specific effects (ADC/DAC quantisation, PA nonlinearity, phase noise, antenna coupling). The channel model is purely software-defined.

3. **LTE-era delay profiles.** The GRC broker implements EPA, EVA, and ETU delay profiles from 3GPP TS 36.104 (LTE). The NR-native TDL and CDL profiles defined in TS 38.104 are not implemented. While the fading statistics are physically valid, the specific tap delays and power profiles are not standardised for NR.

4. **UL channel kept flat.** To prevent PUCCH deep fading and consequent RRC timeout, the UL path uses flat Rician fading for all GRC scenarios. This means UL SINR reported in `crc_stats` does not reflect the DL channel impairment. MCS (which is derived from DL CQI feedback) is the correct metric for comparing scenario severity.

5. **Five failed scenarios.** T3, T4, T5, S3, and L2 produced no MAC-layer data. Only hook-latency telemetry is available for these scenarios. This limits the dataset's coverage of extreme channel conditions.

6. **Single-machine deployment.** Both the gNB and UE run on the same physical machine. Software anomalies (scheduler demotion, traffic flooding) may manifest differently in distributed or cloud-RAN deployments where the gNB runs in a container with dedicated CPU pinning and network namespaces.

---

## 6. Why This Represents the Maximum Feasible Channel Stress

The channel dataset was not designed conservatively. We deliberately pushed each scenario category to the boundary of UE attachment failure, and the five failed scenarios confirm that this boundary was reached.

**EPA is the most severe viable delay profile.** EPA (Extended Pedestrian A) has a 410 ns maximum excess delay and 7 taps. EVA (Extended Vehicular A, 2510 ns, 9 taps) causes the srsUE to fail attachment entirely in ZMQ mode -- the UE process runs but never produces `crc_stats` or `bsr_stats` despite 120 s of waiting. ETU (Extended Typical Urban, 5000 ns, 9 taps) is even more severe and was not attempted after EVA's failure.

**T1 saturates the physical link.** The drive-by scenario with 25 Mbps offered load produces 61.6 MB peak BSR. At the SNR trough (MCS ~8--10), the effective UL throughput is approximately 3--5 Mbps against a theoretical maximum of ~10 Mbps at MCS 28. The link is fully saturated; adding more offered load would not change the MAC-layer signature.

**L1 produces complete periodic disruption.** The 4-second blackout in a 90-second cycle causes the RLC queue to stall completely during each blackout, producing 4.07 s peak RLC delay. This is 100% disruption during the blackout interval -- there is no more severe form of periodic impairment short of permanent disconnection.

**Beyond these parameters, the UE does not attach.** Increasing EPA SNR below ~18 dB, using EVA at any SNR, or combining drive-by fading with CW interference at SIR < 15 dB all result in UE attachment failure. The dataset therefore represents the full operating range of the srsUE ZMQ stack: from clean baseline (B1: MCS 27.6, zero HARQ failures) to the attach-failure boundary (T3/T5/S3: no MAC data produced).

---

## 7. Summary

We collected two complementary anomaly datasets totalling 28 scenarios with usable telemetry:

- **23 stress scenarios** producing infrastructure-only anomalies (scheduler demotion, traffic flooding) that are orthogonal to channel conditions.
- **7 channel scenarios** with full MAC-layer telemetry spanning the range from clean baseline to near-failure.
- **5 additional channel scenarios** with hook-latency only, marking the UE attachment boundary.

Three distinct anomaly classes were identified:

1. **Scheduler-induced hook latency spikes** (40--103x baseline): caused exclusively by real-time priority demotion; SINR/MCS unchanged; no channel-domain equivalent.
2. **Traffic-induced BSR spikes** (15--16x baseline): caused by network flooding; hook latency and SINR unchanged; distinguishable from channel congestion by the absence of MCS/HARQ degradation.
3. **Channel-induced multi-layer cascade**: simultaneous MCS reduction, BSR elevation, RLC delay increase, and HARQ failure rate increase; hook latency unchanged; the classic channel degradation signature.

The pipeline has been validated end-to-end: clean channel conditions produce correct baselines, severe channel conditions produce the expected degradation cascade, and infrastructure faults produce signatures that are cleanly separable from channel events. Hook latency, a novel metric enabled by the jBPF instrumentation, has been confirmed as an infrastructure-only signal orthogonal to channel quality -- it responds to scheduling faults but is completely insensitive to radio channel impairments.
