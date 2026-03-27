# srsRAN 5G Telemetry Pipeline

Real-time telemetry collection, channel emulation, and anomaly dataset collection for a 5G NR gNodeB using eBPF instrumentation (jBPF).

## What This Is

An end-to-end pipeline that:

1. **Instruments** a 5G gNB (srsRAN Project) with ~60 eBPF codelets across MAC, RLC, PDCP, FAPI, RRC, and NGAP layers — extracting 17 telemetry schemas without modifying the gNB source
2. **Emulates** realistic radio channels using a custom ZMQ broker (C or Python) with AWGN, Rician/Rayleigh fading, 3GPP EPA/EVA/ETU multi-tap fading, CFO, burst drops, and CW/narrowband interference injection
3. **Monitors** end-to-end UE performance — DL/UL throughput (iperf3) and ICMP latency alongside MAC-layer telemetry
4. **Visualizes** everything in a 39-panel Grafana dashboard with 5-second auto-refresh, plus an optional real-time QT GUI showing spectrum, constellation, IQ waveform, and waterfall plots
5. **Collects** labeled anomalous datasets using 20+ system-level stress scenarios

## Architecture

```
gNB (jBPF) ──ZMQ──► Channel Broker ──ZMQ──► srsUE ──► iperf3 UL :5201
    │           (fading + AWGN +                  └──► iperf3 DL :5202 (--reverse)
    │            interference)                    └──► ping RTT → /tmp/ping_ue.log
    │
    ├── ~60 eBPF codelets → 17 telemetry schemas
    │
    └── jrtc → gRPC Decoder → /tmp/decoder.log
                                    │
                                    ▼
                        telemetry_to_influxdb.py → InfluxDB → Grafana (39 panels)
```

## Quick Start

```bash
# C broker — Rician fading (recommended, triggers HARQ failures)
./scripts/launch_mac_telemetry.sh --fading

# GRC Python broker — EPA frequency-selective fading
./scripts/launch_mac_telemetry.sh --grc --profile epa --snr 28

# GRC broker with live QT GUI (sliders + spectrum/constellation plots)
./scripts/launch_mac_telemetry.sh --gui --fading

# CW interference at 1 MHz offset, SIR=10 dB
./scripts/launch_mac_telemetry.sh --interference-type cw --sir 10

# Narrowband (1 PRB) interference — automatically uses GRC broker
./scripts/launch_mac_telemetry.sh --interference-type narrowband --sir 15

# Stop everything
./scripts/stop_mac_telemetry.sh

# Collect stress anomaly dataset (20+ scenarios)
./scripts/stress_anomaly_collect.sh --duration 180
```

Open Grafana at `http://localhost:3000` (admin/admin).

## Channel Capabilities

| Feature | C Broker | GRC Python Broker |
|---------|:--------:|:-----------------:|
| AWGN | ✓ | ✓ |
| Flat Rician/Rayleigh fading | ✓ | ✓ |
| 3GPP EPA/EVA/ETU fading | — | ✓ |
| Carrier Frequency Offset (CFO) | — | ✓ |
| Burst error injection | — | ✓ |
| Time-varying scenarios | — | ✓ |
| CW tone interference | ✓ | ✓ |
| Narrowband (1 PRB) interference | — | ✓ |
| Live QT GUI | — | ✓ |

## Validated Interference Results

| SIR (dB) | MAC DL SINR | Ping RTT |
|----------|-------------|----------|
| ∞ (off) | 25.4 dB | ~5 ms |
| 20 | ~20 dB | ~7 s |
| 10 | 3.6 dB | ~39 s |

## Directory Structure

```
scripts/            Pipeline scripts (launch, stop, brokers, ingestor, plotting,
                    stress anomaly collection)
docs/               Technical documentation
  ZMQ_CHANNEL_BROKER_DOCS.md   — Full broker + channel model documentation
  PROJECT_CONTINUATION.md      — Full project reference (phases, schemas, quirks)
codelets/           eBPF codelet sets (11 sets, ~60 programs)
config/             gNB, UE, and broker configuration files
grafana/            Dashboard JSON and provisioning
plots/              Generated telemetry plot PNGs
project_extension/  Dataset extension — docs, figures, and analysis scripts
```

## Documentation
- [Channel Broker Docs](docs/ZMQ_CHANNEL_BROKER_DOCS.md) — Broker architecture, channel models, measured results
- [Project Reference](docs/PROJECT_CONTINUATION.md) — Full project context, all phases, schemas, and data quirks
- [Hook Points Report](docs/JBPF_HOOK_POINTS_REPORT.md) — 68 jBPF instrumentation points

## Prerequisites

- Ubuntu 22.04+
- srsRAN Project with jBPF hooks
- srsRAN 4G (for srsUE)
- GNU Radio 3.10+ with Python bindings (for GRC broker)
- InfluxDB 1.6+, Grafana 11+
- Python 3.8+: numpy, scipy, influxdb, protobuf

## License

Internal research project.
