# jBPF Instrumentation Benchmarking

Measurements of the cost and capability of jBPF codelets during normal 5G NR operation.
All experiments use srsRAN gNB + srsUE over ZMQ on a 16-core x86_64, Ubuntu 22.04.

---

## 1. CPU Overhead

A controlled OFF vs ON experiment was run using `scripts/benchmark_codelet_overhead.sh`. Both runs used an identical setup (jrtc running, gNB + srsUE active, 10 Mbps iperf3 UL) for 90 s after a 25 s stabilisation period. Run A loaded zero codelets; Run B loaded all 12 codelet sets (~60 programs across MAC, RLC, PDCP, FAPI, RRC, NGAP, perf, and custom SINR layers).

| Process | OFF | ON (60 codelets) | Delta |
|---|---|---|---|
| gNB (avg %) | 178.78 | 178.92 | **+0.15** |
| jrtc (avg %) | 9.48 | 9.85 | **+0.37** |
| System — all 16 cores (%) | 18.04 | 18.06 | **+0.02** |

> gNB CPU exceeds 100% because it uses multiple threads; all percentages are relative to one core.

Loading 60 eBPF codelets adds **+0.52% of one core** in total (+0.15% gNB process, +0.37% jrtc proxy). The system-wide delta is within measurement noise.

Raw files: `/tmp/bench_74969/`. Reproduce: `bash scripts/benchmark_codelet_overhead.sh`

---

## 2. Per-Hook Execution Latency

The perf codelet instruments each hook and reports invocation count, p50, p90, p99, and max execution time once per second. CPU cost is estimated as `invocations/s × p50_us / 1e6 × 100`. MAC scheduler hooks (SINR, CQI, TA, RI, BSR, UL BLER sources) are not perf-instrumented; their cost is bounded by the OFF/ON result above.

| Hook | Metric | Inv/s | p50 (µs) | p99 (µs) | CPU % |
|---|---|---:|---:|---:|---:|
| fapi_dl_tti_request | DL MCS | 601 | 1.536 | 6.144 | 0.092 |
| pdcp_dl_new_sdu | data path | 876 | 0.768 | 6.144 | 0.067 |
| rlc_dl_new_sdu | data path | 876 | 0.768 | 6.144 | 0.067 |
| fapi_ul_tti_request | UL MCS | 601 | 0.768 | 3.072 | 0.046 |
| pdcp_dl_tx_data_pdu | data path | 876 | 0.384 | 3.072 | 0.034 |
| rlc_dl_sdu_send_completed | data path | 876 | 0.384 | 3.072 | 0.034 |
| rlc_dl_sdu_send_started | data path | 876 | 0.384 | 3.072 | 0.034 |
| rlc_ul_rx_pdu | data path | 1180 | 0.192 | 3.072 | 0.023 |
| rlc_dl_tx_pdu | data path | 1111 | 0.192 | 3.072 | 0.021 |
| pdcp_ul_deliver_sdu | data path | 876 | 0.192 | 3.072 | 0.017 |
| pdcp_ul_rx_data_pdu | data path | 876 | 0.192 | 6.144 | 0.017 |
| rlc_ul_sdu_delivered | data path | 876 | 0.192 | 6.144 | 0.017 |
| rlc_dl_sdu_delivered | data path | 876 | 0.096 | 3.072 | 0.008 |
| rlc_dl_am_tx_pdu_retx_count | retx | 2 | 0.096 | 1.536 | <0.001 |
| **Total (14 perf-instrumented hooks)** | | | | | **0.477** |

All data-plane hooks execute in **≤ 1.5 µs median** and **≤ 6 µs p99** — well under the 1 ms slot budget. FAPI hooks fire per scheduled TTI (not every slot); at 10 MHz / 5 Mbps DL this is ~601/s. The worst recorded single invocation across all data-plane hooks was **70.7 µs** (`fapi_ul_tti_request`), less than 10% of one slot.

### Hook Latency as a Fault Indicator

During scheduler fault scenarios, `fapi_ul_tti_request` p99 spikes from its 6 µs baseline to **7,289 µs — a 1,214× increase**. This spike is invisible to standard srsRAN metrics (SINR, MCS, and BLER remain normal throughout). Hook execution latency is therefore a novel fault signal not accessible through any standard telemetry path.

---

## 3. jBPF vs Standard Pipeline Comparison

All numbers are from a 41-minute session (10:20–11:01 UTC). Analysis script: `scripts/measure_pipeline_latency.py`.

### Reporting Freshness

Both pipelines aggregate over a 1 s window, but the standard pipeline uses an additional asynchronous WebSocket push + Telegraf processing step, causing it to miss roughly one in three gNB update cycles.

| Metric | jBPF interval (s) | Standard interval (s) | jBPF leads by |
|---|---:|---:|---:|
| SINR / SNR | 1.074 | 1.634 | **+0.75 s** |
| UL BLER | 1.074 | 1.634 | **+0.75 s** |
| Timing Advance | 1.073 | 1.634 | **+0.75 s** |
| BSR | 1.074 | 1.634 | **+0.75 s** |
| UL MCS | 1.074 | 1.634 | **+0.75 s** |
| DL MCS | 1.074 | 1.634 | **+1.00 s** |
| CQI / RI | 1.073 | 1.634 | n/a (constant value) |

The "jBPF leads by" column is the cross-correlation lag measured by interpolating both series to a 0.25 s grid and finding the time shift at peak correlation. jBPF delivers MAC and FAPI metrics **36% more frequently** and the same signal arrives **0.75–1.00 s earlier** on average.

### Per-Metric Overhead

For jBPF, every metric is produced by a specific hook executing synchronously inside the gNB. For the standard pipeline, the gNB computes all metrics internally regardless of whether Telegraf is running; Telegraf's single WebSocket poll covers every metric in one pass with no per-metric attribution. The table below shows the per-metric cost in each pipeline.

| Metric | jBPF hook | jBPF inv/s | jBPF p50 (µs) | jBPF CPU % | Standard mechanism | Std CPU % |
|---|---|---:|---:|---:|---|---:|
| SINR / SNR | mac_sched_crc_indication | — | — | bounded by §1 | gNB internal → WebSocket | ~0 |
| UL BLER | mac_sched_crc_indication | — | — | bounded by §1 | gNB internal → WebSocket | ~0 |
| CQI | mac_sched_uci_indication | — | — | bounded by §1 | gNB internal → WebSocket | ~0 |
| Timing Advance | mac_sched_uci_indication | — | — | bounded by §1 | gNB internal → WebSocket | ~0 |
| Rank Indicator | mac_sched_uci_indication | — | — | bounded by §1 | gNB internal → WebSocket | ~0 |
| BSR | mac_sched_ul_bsr | — | — | bounded by §1 | gNB internal → WebSocket | ~0 |
| DL MCS | fapi_dl_tti_request | 601 | 1.536 | **0.092** | gNB internal → WebSocket | ~0 |
| UL MCS | fapi_ul_tti_request | 601 | 0.768 | **0.046** | gNB internal → WebSocket | ~0 |
| DL Throughput | iperf3 stdout reader | — | — | ~0 | gNB scheduler rate → WebSocket | ~0 |
| UL Throughput | iperf3 stdout reader | — | — | ~0 | gNB scheduler rate → WebSocket | ~0 |

The six MAC-layer hooks are not individually instrumented by the perf codelet; their combined cost is bounded by the OFF/ON result in §1 (<0.52% for all 60 codelets). The only metrics with a precisely measured per-hook cost are DL MCS and UL MCS. The standard pipeline costs effectively zero per individual metric — the entire Telegraf process averages **~0.13% of one core** at idle regardless of how many metrics it collects.

### Total Pipeline Overhead

| Component | Pipeline | CPU (% of 1 core) | Condition |
|---|---|---:|---|
| gNB process delta | jBPF | +0.14 | active, 10 Mbps UL |
| jrtc proxy | jBPF | +0.37 | active, 10 Mbps UL |
| **jBPF total** | jBPF | **+0.51** | active, 10 Mbps UL |
| Telegraf + ws_adapter.py | Standard | ~0.13 | idle (no active gNB) |

jBPF costs roughly **+0.38 percentage points more** than the standard pipeline. In exchange it delivers metrics 0.75–1.00 s earlier, updates 36% more frequently, and exposes signals — hook execution latency, per-slot SINR range, HARQ retransmissions — not available through the WebSocket.

---

## 4. Bandwidth Saving — In-Hook Analytics

The custom SINR codelet (`mac_sched_crc_stats_custom`) computes variance and a 16-sample sliding window average **inside the hook** rather than shipping raw per-slot samples.

| Approach | Rate (per UE) |
|---|---|
| Raw per-slot shipping (1 int32 + index + timestamp per ms slot) | ~16,000 bytes/s |
| Custom in-hook codelet (one aggregated Protobuf per second, 11 fields) | ~52 bytes/s |

**308× reduction. Bandwidth saved: 99.7%.** The saving scales linearly with the number of UEs.

Every 1 ms slot the hook accumulates `sum_sinr`, `sum_sq_sinr`, `cnt`, `min`, `max` in a BPF map and updates a 16-entry circular buffer for the sliding average (O(1), no stored history). Once per second the collector serialises the map into a single Protobuf message sent via UDP:

```
t_crc_stats_custom {
  du_ue_index, succ_tx, cnt_tx,
  min_sinr, max_sinr, sum_sinr, cnt_sinr,
  sum_sq_sinr, sinr_variance,          // variance: E[X²] - E[X]²
  sinr_sliding_avg, sinr_sliding_cnt   // 16-sample window
}
```
