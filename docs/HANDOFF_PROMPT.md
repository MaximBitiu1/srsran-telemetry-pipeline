# AI Handoff Prompt — srsRAN 5G jBPF Telemetry Thesis Project

> Feed this document to any AI model to resume the thesis work from exactly where we left off.
> Working machine: Ubuntu 22.04, user `maxim`, primary workspace `~/Desktop/srsran-telemetry-pipeline/`

---

## 1. Who I Am and What This Is

I'm a thesis student building a **5G NR telemetry and anomaly detection pipeline** using srsRAN Project (a software gNB) instrumented with **jBPF** (eBPF codelets injected at runtime into gNB function call sites). The thesis is about demonstrating that jBPF-level telemetry provides information that the standard srsRAN metrics channel cannot — particularly for detecting infrastructure-level faults invisible to radio-layer monitoring.

My setup runs entirely on one Ubuntu 22.04 machine. No physical RF hardware — the gNB talks to a software UE (srsUE) through a custom ZMQ channel broker that injects calibrated RF impairments.

---

## 2. Full System Architecture

```
jrtc (jBPF runtime controller — must start FIRST)
  |
  +-- gNB (srsRAN Project, jBPF fork at ~/Desktop/srsRAN_Project_jbpf/)
  |     TX :4000  RX :4001
  |         |
  |    ZMQ Channel Broker (GRC Python: ~/Desktop/srsran-telemetry-pipeline/scripts/grc_channel_broker.py)
  |    (fading, AWGN, interference injection)
  |         |
  |     srsUE (NR-only, net namespace ue1)
  |       TX :2001  RX :2000
  |       TUN: tun_srsue (10.45.0.1/24)
  |         +-- iperf3 UL :5201  (10 Mbps UDP, UE -> core)
  |         +-- iperf3 DL :5202  (5 Mbps UDP, core -> UE)
  |         +-- ICMP ping
  |
  +-- ~60 eBPF codelets (11 sets via jrtc-ctl) -> 17 telemetry schemas
  |
  +-- Reverse Proxy :30450 (IPC-to-TCP bridge between gNB and decoder)
  |
  +-- Decoder (gRPC :20789, UDP :20788)
        -> /tmp/decoder.log
        -> scripts/telemetry_to_influxdb.py -> InfluxDB 1.x :8086
                                              (database: srsran_telemetry)
                                              -> Grafana :3000 (36 panels)
                                                 http://localhost:3000/d/srsran-5g-nr-telemetry/srsran-5g-nr-telemetry

SECOND metrics channel (standard srsRAN):
  gNB remote_control service (WebSocket :8001)
    -> ~/Desktop/capture_standard_metrics.py (subscribe + write to /tmp/standard_metrics.jsonl)
    -> Used for live comparison with jBPF telemetry
```

### Key Config File
- **gNB config**: `~/Desktop/srsRAN_Project_jbpf/configs/gnb_zmq_jbpf.yml`
  - `jbpf_ipc_mem_name: "jrt_controller"` — shared memory for jrtc
  - `jbpf_enable_lcm_ipc: 1` and `jbpf_lcm_ipc_name: "jbpf_lcm_ipc"` — LCM socket (gNB creates this)
  - `remote_control: enabled: true, bind_addr: "127.0.0.1", port: 8001` — standard WebSocket metrics
  - `metrics: enable_json: true` — enables JSON metrics on the WebSocket (correct key is `enable_json`, NOT `enable_json_metrics` or `enable_metrics_subscription`)

### Launch / Stop
```bash
# Start full pipeline (fading channel scenario)
bash ~/Desktop/launch_mac_telemetry.sh --fading --k-factor 3 --snr 25

# Stop everything cleanly
bash ~/Desktop/stop_mac_telemetry.sh

# Capture standard WebSocket metrics in parallel
python3 ~/Desktop/capture_standard_metrics.py > /tmp/ws_capture.log 2>&1 &
# Records to /tmp/standard_metrics.jsonl (one JSON line per second)
```

**IMPORTANT known issue:** The launch script waits for `/tmp/jbpf/jbpf_lcm_ipc` to appear within 20s. If the gNB config has an invalid YAML key, the gNB silently fails and that socket never appears. Always check `/tmp/gnb_stderr.log` first if the launch fails with "IPC socket did not appear within 20s".

---

## 3. jBPF Telemetry — 17 Schemas

jBPF instruments 22 function call sites producing 17 Protobuf schemas (decoded by the decoder process):

| Schema | Key fields | Typical rate |
|--------|-----------|--------------|
| `harq_stats` | `avg_mcs`, `mcs_min`, `mcs_max`, `cons_retx`, `fail_rate`, `stream_id` | 2/s (2 MIMO streams → aggregated to 1/s) |
| `crc_stats` | `sinr_avg`, `harq_fail`, `success_rate` | 1/s |
| `bsr_stats` | `bsr_kb` | 1/s per BSR report |
| `jbpf_out_perf_list` | `hook_name`, `p50_us`, `p90_us`, `p95_us`, `p99_us`, `max_us`, `num` | 7 hooks at 1/s steady state + 15 event hooks |
| `rlc_ul_stats` | `sdu_delivered_bytes_total` (cumulative), `pdu_bytes_total` (cumulative), `sdu_latency_avg_us`, `sdu_latency_max_us`, `rb_id`, `is_srb` | 1/s |
| `rlc_dl_stats` | similar | 1/s |
| `pdcp_ul_stats` | throughput, SDU latency | 1/s |
| `pdcp_dl_stats` | similar | 1/s |
| `rach_stats` | preamble SNR, timing advance per RACH attempt | per event |
| `rrc_ue_procedure` | procedure type, timing | per event |
| `ngap_procedure_started/completed` | NG-AP round-trip | per event |
| `dl_stats` (PDCP DL) | `dataPduRetxBytes` | 1/s |
| `fapi_ul/dl` | scheduler MCS, PRB usage, TBS | per slot (1ms) |

**Steady-state hooks in perf_list** (always firing at traffic load):
`fapi_ul_tti_request`, `fapi_dl_tti_request`, `pdcp_ul_deliver_sdu`, `pdcp_ul_rx_data_pdu`, `rlc_ul_rx_pdu`, `rlc_ul_sdu_delivered`, `rlc_dl_tx_pdu`

**CPU overhead:** ~3.3% of 1 CPU core at 25 Mbps load (~33 µs/slot). Full breakdown in `docs/JBPF_VS_STANDARD_TELEMETRY.md`.

---

## 4. Standard srsRAN Metrics Channel

The gNB exposes a second, independent metrics stream via WebSocket at `ws://127.0.0.1:8001`.
- Connect with `{"cmd": "metrics_subscribe"}` on connect
- Receives JSON every ~1 second: `du.du_high.mac`, `cells[].ue_list[]`
- Per-UE fields: `dl_mcs`, `ul_mcs`, `pusch_snr_db` (SINR), `bsr`, `cqi`, `dl_brate`, `ul_brate`, `dl_nof_ok`, `dl_nof_nok` (HARQ), `ta_ns`
- These are **~1s aggregates**, no per-slot resolution, no hook latency, no infrastructure fault visibility
- Capture script: `~/Desktop/capture_standard_metrics.py` → `/tmp/standard_metrics.jsonl`
- Requires `pip3 install websocket-client`

---

## 5. Datasets — What We Built

### Location
All datasets live at: `~/Desktop/srsran-telemetry-pipeline/datasets/`

### 5.1 Stress Anomaly Dataset
- **Raw CSVs**: `datasets/stress_anomaly/csv/` (6 files: harq, crc, bsr, perf, rlc_ul, rlc_dl)
- **Cleaned feature matrix**: `datasets/stress_anomaly/stress_features.csv` (2892 rows × 49 cols)
- **Collection script**: `scripts/stress_anomaly_collect.sh` — 23 scenarios across 4 categories:
  - `cpu_memory`: CPU stress, memory pressure, NUMA binding, NUMA interleave
  - `scheduling`: RT→batch demotion (various thread combos), throttling, sleep injection, affinity pinning
  - `traffic_flood`: UDP 10M/50M/100M, TCP, burst, SYN flood, ICMP flood, DNS amplification
  - `normal`: clean baseline
- **Scenario IDs 0–22** (0–11 and 21 = normal, 12–14 and 22 = scheduler_fault, 15–20 = traffic_flood)

### 5.2 Channel Dataset
- **Raw CSVs**: `datasets/channel/csv/` (17 files matching the 17 telemetry schemas)
- **Cleaned feature matrix**: `datasets/channel/channel_features.csv` (2729 rows × 49 cols)
- **Scenarios**: B1, B2 (baselines), T1–T5 (time-varying/drive-by), S1–S3 (steady impairment), L1–L2 (RLF/link failure cycles)
- **Labels**: normal = [B1, S2], channel_degradation = [B2, T1, T2, S1, L1, T3, T4, T5, S3, L2]

### 5.3 Finalized ML-Ready Dataset
| File | Description |
|------|-------------|
| `datasets/combined_labelled.csv` | 5621 rows × 26 cols. Both datasets merged with 4-class labels |
| `datasets/train_features.csv` | 4487 rows, scenario-based split |
| `datasets/test_features.csv` | 1134 rows, held-out scenarios |
| `datasets/feature_scaler.json` | Min/max scaler parameters per feature |
| `datasets/class_map.json` | `{0: normal, 1: scheduler_fault, 2: traffic_flood, 3: channel_degradation}` |

**19 features used:**
`hook_p99_us_fapi_ul_tti_request`, `hook_p99_us_fapi_dl_tti_request`, `hook_p99_us_pdcp_ul_deliver_sdu`, `hook_p99_us_pdcp_ul_rx_data_pdu`, `hook_p99_us_rlc_ul_rx_pdu`, `hook_p99_us_rlc_ul_sdu_delivered`, `hook_p99_us_rlc_dl_tx_pdu`, `hook_max_us_fapi_ul_tti_request`, `harq_mcs_avg`, `harq_mcs_min`, `harq_cons_retx`, `harq_fail_rate`, `crc_sinr_avg`, `crc_harq_fail`, `crc_success_rate`, `bsr_kb`, `rlc_throughput_kb`, `rlc_lat_avg_us`, `rlc_lat_max_us`

**Key insight:** `hook_p99_us_fapi_ul_tti_request` is the single best discriminator for scheduler faults — it spikes to 7000+ µs (7× the 1ms slot budget) during RT→batch scheduler demotion, while being invisible to the standard metrics channel entirely.

### Scripts
| Script | Purpose |
|--------|---------|
| `scripts/clean_datasets.py` | Cleans raw CSVs: aggregates HARQ MIMO streams, pivots perf_list to wide, diffs RLC cumulative counters |
| `scripts/finalize_dataset.py` | Applies 4-class labels, fills NaN, scenario-based train/test split, saves scaler |
| `scripts/export_channel_dataset.py` | Exports raw decoder logs to structured CSVs/HDF5 |
| `scripts/plot_all_scenarios.py` | Plots per-scenario time series |
| `scripts/plot_stress_comparison.py` | 7-panel cross-scenario comparison (stress anomaly) |
| `scripts/plot_standard_vs_jbpf.py` | Side-by-side comparison plots for thesis |
| `scripts/plot_today_channel.py` | Per-scenario plots for channel dataset |

---

## 6. What We Have Done — Completed Tasks

### Task A — Data Collection (DONE)
- Collected 23 stress anomaly scenarios with `stress_anomaly_collect.sh`
- Collected 12 realistic channel scenarios (B1, B2, T1–T5, S1–S3, L1–L2) with `collect_channel_realistic.sh`
- Also collected 7 additional scenarios on 2026-04-02 (T3, T4, T5, S1, S3 re-runs, L2)
- All raw data backed up in `csv_raw/` folders

### Task 1/Part A — Clean and Finalize Datasets (DONE)
- `clean_datasets.py`: cleans and merges all 6 raw CSV files into feature matrices (stress_features.csv, channel_features.csv)
- `finalize_dataset.py`: 4-class labels, NaN handling, scenario-based split, scaler
- Datasets fully ready for ML training (even though no model training is planned for thesis — data is thesis artifact)

### Task 2 — jBPF vs Standard Telemetry Comparison (IN PROGRESS — 80% done)
- **Theoretical comparison** fully documented in `docs/JBPF_VS_STANDARD_TELEMETRY.md`
- **CPU overhead table** computed from perf_list data and written to that doc
- **gNB config fixed** to enable WebSocket metrics server: `remote_control: {enabled: true, port: 8001}` + `metrics: {enable_json: true}` (note: the key `enable_json` is correct; `enable_metrics_subscription` and `enable_json_metrics` are NOT valid YAML keys for this srsRAN version)
- **Capture script created**: `~/Desktop/capture_standard_metrics.py` (requires `websocket-client`)
- **REMAINING**: Need to run the pipeline live, capture both streams simultaneously, trigger a scheduler demotion anomaly, then generate comparison plots with `scripts/plot_standard_vs_jbpf.py`

### Task 3 — Codelet Math (NOT STARTED)
- Plan: pick `fapi_ul_tti_request` codelet, implement **variance** and **sliding window average** of p99 hook latency directly inside the eBPF codelet C code
- Codelet files are at `~/Desktop/jrtc-apps/codelets/`
- This demonstrates in-network (gNB-side) analytics capability of jBPF

### Task 4 — Thesis Report (NOT STARTED)
- Add all findings to the thesis document
- Key sections needed: system architecture, telemetry pipeline description, dataset description, jBPF vs standard comparison, CPU overhead analysis, codelet math demo

---

## 7. Remaining Work (Prioritized)

### 7.1 Complete Task 2 — Live Comparison
```bash
# 1. Start pipeline
bash ~/Desktop/launch_mac_telemetry.sh --fading --k-factor 3 --snr 25

# 2. In parallel, start standard metrics capture
pip3 install websocket-client  # if not installed
python3 ~/Desktop/capture_standard_metrics.py > /tmp/ws_capture.log 2>&1 &

# 3. Wait ~90s for baseline (UE attached, iperf3 running)
# Record start time: date -u +%Y-%m-%dT%H:%M:%SZ

# 4. Trigger scheduler demotion (scheduler_fault scenario)
# Find gNB PID and demote its threads from SCHED_FIFO:96 to SCHED_BATCH
sudo chrt --batch -p 0 $(pgrep -x gnb) 2>/dev/null
# Or more precisely: demote all RT threads of gNB
for pid in $(ps -eLo pid,cls,pri,comm | awk '$2=="FF" && $4~/gnb/{print $1}' | sort -u); do
  sudo chrt --batch -p 0 $pid 2>/dev/null
done

# 5. Wait ~90s during anomaly

# 6. Stop pipeline, then fetch data from InfluxDB and /tmp/standard_metrics.jsonl
# Run: python3 ~/Desktop/srsran-telemetry-pipeline/scripts/plot_standard_vs_jbpf.py

# 7. Restore gNB scheduling (or just stop pipeline)
bash ~/Desktop/stop_mac_telemetry.sh
```

**What to expect:**
- Standard metrics will show slight MCS drop, BSR increase — looks like minor channel degradation
- jBPF `hook_p99_us_fapi_ul` will spike to 7000+ µs — clearly identifying scheduler fault
- This difference is the core thesis result

### 7.2 Task 3 — Codelet Variance/Sliding Window
- Find `fapi_ul_tti_request` codelet: look in `~/Desktop/jrtc-apps/codelets/`
- Add two new output fields to the codelet's map: `p99_variance` and `p99_sliding_avg_10`
- Implement a simple circular buffer + running variance in C inside the codelet
- Rebuild with `make` in `~/Desktop/jrtc-apps/`
- Re-run pipeline and verify new fields appear in decoder output

### 7.3 Task 4 — Thesis Report
Add sections to the thesis document covering:
1. System architecture (use the ASCII diagram from `docs/PROJECT_REFERENCE.md`)
2. jBPF hook list and what each captures (from `docs/JBPF_HOOK_POINTS_REPORT.md`)
3. Dataset description and collection methodology (from `docs/ANOMALY_COLLECTION_REPORT.md`)
4. jBPF vs standard comparison with live plots (from `docs/JBPF_VS_STANDARD_TELEMETRY.md`)
5. CPU overhead analysis (from same doc, Section 4)
6. Codelet math demonstration (Task 3 result)

---

## 8. Key Documents (read these for full context)

| Document | Content |
|----------|---------|
| `~/Desktop/srsran-telemetry-pipeline/docs/PROJECT_REFERENCE.md` | Full system reference: architecture, all scripts, all components, config details |
| `~/Desktop/srsran-telemetry-pipeline/docs/ANOMALY_COLLECTION_REPORT.md` | All 23 stress + 12 channel scenarios with per-scenario explanations, plots, and collection notes |
| `~/Desktop/srsran-telemetry-pipeline/docs/JBPF_VS_STANDARD_TELEMETRY.md` | jBPF vs standard comparison, CPU overhead table, panel comparison |
| `~/Desktop/srsran-telemetry-pipeline/docs/JBPF_HOOK_POINTS_REPORT.md` | Full list of all ~60 jBPF hook points, what each one instruments |
| `~/Desktop/srsran-telemetry-pipeline/docs/ZMQ_CHANNEL_BROKER_DOCS.md` | Channel broker documentation, fading models, scenario parameters |
| `~/Desktop/srsran-telemetry-pipeline/docs/JBPF_MAC_TELEMETRY_PROMPT.md` | Original system prompt describing the full pipeline (early reference) |
| `~/Desktop/srsran-telemetry-pipeline/datasets/README.md` | Full per-column schema docs for all 17 CSV files, scenario tables, Python loading example |
| `~/Desktop/srsran-telemetry-pipeline/datasets/class_map.json` | `{0: normal, 1: scheduler_fault, 2: traffic_flood, 3: channel_degradation}` |

---

## 9. Important Technical Notes

- **jrtc must start BEFORE gNB** — the IPC socket (`/tmp/jbpf/jbpf_lcm_ipc`) is created by the gNB only after it connects to jrtc's shared memory. If jrtc isn't running, gNB starts but never creates the LCM socket.
- **gNB config YAML keys for WebSocket**: valid keys are `remote_control: {enabled, bind_addr, port}` and `metrics: {enable_json: true}`. Do NOT use `enable_metrics_subscription` under `remote_control` or `enable_json_metrics` under `metrics` — both cause gNB to refuse to start with "INI was not able to parse" error.
- **harq_stats has 2 rows/second** (stream_id 0 and 1, MIMO). Must aggregate before merging with other 1/s schemas.
- **rlc_ul_stats byte fields are cumulative counters** — must diff within each scenario before use.
- **perf_list has event hooks** (RACH, RRC, NGAP) that only fire during attach/detach. The 7 steady-state hooks are the ones useful for anomaly detection.
- **UE IP**: The launch script uses `UE_IP` variable derived from `ip -n ue1 addr show tun_srsue`. This variable must be set before the `iperf3` step — there was a previous bug where it was unbound; the Desktop copy of `launch_mac_telemetry.sh` has this fixed.
- **InfluxDB**: Version 1.x, database `srsran_telemetry`. Query: `curl "http://localhost:8086/query?db=srsran_telemetry&q=SHOW+MEASUREMENTS"`. Time range filters use RFC3339 strings.
- **Datasets are in git**: `~/Desktop/srsran-telemetry-pipeline/` is a git repository. All scripts, docs, and dataset files (except large raw logs) are committed.

---

## 10. Git State

Repository: `~/Desktop/srsran-telemetry-pipeline/`

Last major commits included:
- All dataset CSV files (stress_features.csv, channel_features.csv, combined_labelled.csv, train/test splits)
- All scripts (clean_datasets.py, finalize_dataset.py, plot_*.py)
- Full docs rewrite (README.md, ANOMALY_COLLECTION_REPORT.md, JBPF_VS_STANDARD_TELEMETRY.md)

To check current state: `cd ~/Desktop/srsran-telemetry-pipeline && git log --oneline -10 && git status`

---

*End of handoff prompt. The most urgent remaining task is completing Task 2 (live comparison) — the pipeline config is fixed and ready, just needs to be run and plots generated.*
