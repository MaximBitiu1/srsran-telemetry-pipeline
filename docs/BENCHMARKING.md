# jBPF Instrumentation Benchmarking

Measurement of the cost and overhead introduced by jBPF codelets during normal 5G NR operation,
and the bandwidth saving achieved by the custom in-hook analytics codelet.

All measurements are derived from telemetry collected during real pipeline runs using the
`jbpf_out_perf_list` hook latency stream. The observation method is described in
[Hook Points Report](JBPF_HOOK_POINTS_REPORT.md).

---

## 1. CPU Overhead

### Method

The perf codelets record the execution time of every hook invocation and report per-hook statistics
(count, p50, p90, p99, max) once per second. CPU overhead is estimated as:

```
CPU_fraction = sum_over_hooks( invocations_i * p50_exec_time_i ) / (window_s * 1e6 us)
```

`p50` (median) is used as a conservative proxy for mean execution time. This is a lower bound
because the MAC scheduler hooks (`mac_sched_crc_indication`, `mac_sched_ul_phr`, etc.) are not
instrumented by the perf codelet and their overhead is not included.

### Results

**Stress anomaly dataset — baseline scenarios (122 s observation window)**

| Hook | Invocations | p50 (µs) | p99 (µs) | Max (µs) | CPU % |
|---|---:|---:|---:|---:|---:|
| rlc_ul_rx_pdu | 128,203 | 1.536 | 6.144 | 49.5 | 0.161 |
| rlc_ul_sdu_delivered | 107,380 | 1.536 | 6.144 | 47.6 | 0.135 |
| pdcp_ul_deliver_sdu | 107,379 | 1.536 | 6.144 | 40.4 | 0.135 |
| pdcp_ul_rx_data_pdu | 107,379 | 1.536 | 6.144 | 34.8 | 0.135 |
| fapi_dl_tti_request | 82,958 | 1.536 | 6.144 | 45.2 | 0.104 |
| fapi_ul_tti_request | 82,958 | 1.536 | 6.144 | 70.7 | 0.104 |
| rlc_dl_tx_pdu | 6,700 | 3.072 | 12.288 | 36.0 | 0.017 |
| rrc / ngap / e1 / cucp (rare control) | ~40 total | 6–25 | 12–25 | 31 | <0.001 |
| **Total (22 hooks)** | **623,072** | — | — | — | **0.79%** |

**Channel dataset — baseline scenarios (118 s observation window)**

Total invocations: 2,667,493 across 22 hooks. CPU overhead: **0.59%**.

### Interpretation

- All high-frequency hooks (RLC, PDCP, FAPI) execute in **1.5 µs median** — well under the 1 ms
  slot budget.
- The p99 stays at or below **6 µs** for every data-plane hook, meaning fewer than 1% of
  invocations take longer than 6 µs.
- The worst-case single invocation across all data-plane hooks was **70.7 µs**
  (`fapi_ul_tti_request`), still less than 10% of one slot.
- Control-plane hooks (RRC/NGAP setup) run in 6–25 µs but fire only a handful of times per
  session and contribute negligible CPU.
- Measured CPU overhead is **< 1%** of one core across both datasets.

> **Note on methodology**: this is an analytical estimate derived from telemetry, not a direct
> OFF/ON experiment. A direct measurement would require running the same iperf3 session twice
> (once with no codelets loaded, once with all codelets loaded) and comparing CPU samples from
> `mpstat` or `perf stat`. The telemetry-derived estimate is consistent with the eBPF literature
> which reports sub-1% overhead for in-kernel hook programs of this complexity.

---

## 2. Hook Latency as a Fault Indicator

During scheduler fault scenarios, `hook_p99_us_fapi_ul_tti_request` spikes from its 6 µs
baseline to **7,289 µs** — a **1,214× increase** (or 103× above the p99 baseline of 70.7 µs).
This spike is invisible to standard srsRAN metrics (SINR, MCS, BLER remain normal during the
fault). This demonstrates that hook execution latency is a novel fault signal not available
through any standard telemetry path.

---

## 3. Bandwidth Saving — In-Hook Analytics

### Setup

The custom SINR codelet (`mac_sched_crc_stats_custom`) computes variance and a 16-sample sliding
window average **inside the jBPF hook** rather than shipping raw per-slot SINR samples to
InfluxDB for external processing.

### Comparison

| Approach | Data transmitted | Rate (1 UE) |
|---|---|---|
| Raw per-slot shipping | One int32 SINR value per 1 ms slot + index + timestamp | ~16,000 bytes/s |
| Custom codelet (in-hook) | One aggregated report per second (11 fields × 4 bytes + 8-byte timestamp) | ~52 bytes/s |

**Reduction: 308× fewer bytes. Bandwidth saved: 99.7%.**

### How it works

Every 1 ms slot the hook fires and:
1. Accumulates `sum_sinr`, `sum_sq_sinr`, `cnt_sinr`, `min_sinr`, `max_sinr` in a BPF map.
2. Updates a 16-entry circular ring buffer and recomputes the sliding average (O(1)).
3. Computes running variance as `E[X²] - E[X]²` (Welford-style, no stored history).

Once per second the collector codelet serialises the BPF map contents into a single Protobuf
message and sends it via UDP. The raw sample stream is never transmitted.

### Proto output (per UE per second)

```
t_crc_stats_custom {
  du_ue_index, succ_tx, cnt_tx,
  min_sinr, max_sinr, sum_sinr, cnt_sinr,   // same as standard codelet
  sum_sq_sinr,                               // NEW: for variance
  sinr_variance,                             // NEW: E[X^2] - E[X]^2
  sinr_sliding_avg, sinr_sliding_cnt         // NEW: 16-sample window
}
```

The saving scales linearly with the number of UEs and the reporting window length.

---

## 4. Summary

| Metric | Value |
|---|---|
| Hook execution overhead (CPU) | < 1% of one core |
| Median hook execution time (data plane) | 1.5 µs |
| p99 hook execution time (data plane) | 6 µs |
| Worst-case single invocation (baseline) | 70.7 µs |
| Scheduler fault hook latency spike | 7,289 µs (1,214× baseline) |
| Bandwidth saving (in-hook analytics) | 99.7% (308× reduction) |
| Raw data rate without in-hook processing | ~16,000 bytes/s per UE |
| In-hook analytics data rate | ~52 bytes/s per UE |
