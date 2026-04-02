# Datasets

This directory contains exported CSV data and plots from two telemetry collection campaigns.

## Stress Anomaly Dataset (`stress_anomaly/`)

23 scenarios collected on 2026-03-25 using srsRAN 5G NR with jBPF telemetry hooks.
Each scenario runs the gNB under a specific system-level stressor (CPU contention,
memory pressure, scheduler demotion, traffic flooding, or combinations) while
recording MAC/RLC/hook-latency metrics at 1 Hz. The baseline scenario (00) has no
stressor applied. See [ANOMALY_DATASET.md](../docs/ANOMALY_DATASET.md) for full
methodology and per-scenario descriptions.

- **csv/**: 6 schema CSVs (crc_stats, bsr_stats, harq_stats, jbpf_out_perf_list, rlc_ul_stats, uci_stats)
- **plots/**: Per-scenario time-series plots and a cross-scenario summary

## Channel Dataset (`channel/`)

12 scenarios collected on 2026-04-01 using GNU Radio channel emulation (EPA/EVA fading,
Doppler, interference, RLF cycles) with live srsRAN gNB + UE traffic. Scenarios span
baseline, time-varying, steady-impairment, and RLF-cycle categories. Seven scenarios
have full MAC-layer data; five have only jBPF hook latency (no UE was connected or
it crashed early).

- **csv/**: 6 schema CSVs (same schemas as stress dataset)
- **plots/**: Per-scenario time-series plots and a cross-scenario summary
