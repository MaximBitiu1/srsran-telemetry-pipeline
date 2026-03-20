# srsRAN 5G NR Telemetry Pipeline

Real-time telemetry collection and channel emulation for a 5G NR gNodeB using eBPF instrumentation (jBPF).

## What This Is

An end-to-end pipeline that:

1. **Instruments** a 5G gNB (srsRAN Project) with ~60 eBPF codelets across MAC, RLC, PDCP, FAPI, RRC, and NGAP layers — extracting 17 telemetry schemas without modifying the gNB source
2. **Emulates** realistic radio channels using a GNU Radio Python broker with AWGN, Rician/Rayleigh fading, 3GPP EPA/EVA/ETU multi-tap fading, CFO, burst drops, and time-varying scenarios
3. **Visualizes** everything in a 39-panel Grafana dashboard with 5-second auto-refresh, plus an optional real-time QT GUI showing spectrum, constellation, IQ waveform, and waterfall plots

## Architecture

```
gNB (jBPF) ──ZMQ──► GRC Channel Broker ──ZMQ──► srsUE ──► iperf3
    │                (fading + AWGN)                         (10 Mbps UDP)
    │
    ├── 60 eBPF codelets → 17 telemetry schemas
    │
    └── jrtc → gRPC Decoder → /tmp/decoder.log
                                    │
                                    ▼
                        telemetry_to_influxdb.py → InfluxDB → Grafana (39 panels)
```

## Quick Start

```bash
# Launch full pipeline with Rician fading (recommended)
./scripts/launch_mac_telemetry.sh --grc --fading --snr 28 --k-factor 3 --doppler 5

# With GUI (interactive sliders + real-time signal plots)
./scripts/launch_mac_telemetry.sh --gui --fading --snr 25 --k-factor 1 --doppler 10

# Stop everything
./scripts/stop_mac_telemetry.sh
```

Open Grafana at `http://localhost:3000` (admin/admin).

## Channel Capabilities

| Feature | C Broker | Python GRC Broker |
|---------|:--------:|:-----------------:|
| AWGN | ✓ | ✓ |
| Flat Rician/Rayleigh fading | ✓ | ✓ |
| 3GPP EPA/EVA/ETU fading | — | ✓ |
| Carrier Frequency Offset | — | ✓ |
| Burst error injection | — | ✓ |
| Time-varying scenarios | — | ✓ |
| Live QT GUI | — | ✓ |

## Directory Structure

```
scripts/          Pipeline scripts (launch, stop, broker, ingestor, plotting)
docs/             Technical documentation and reports
codelets/         eBPF codelet sets (11 sets, ~60 programs)
config/           gNB, UE, and broker configuration files
grafana/          Dashboard JSON and provisioning
plots/            Generated telemetry plot PNGs
```

## Documentation

- [Supervisor Report](docs/SUPERVISOR_REPORT.md) — Comprehensive project overview
- [Channel Broker Docs](docs/ZMQ_CHANNEL_BROKER_DOCS.md) — Detailed broker documentation
- [AI Continuation Prompt](docs/AI_CONTINUATION_PROMPT.md) — Session handoff document
- [Hook Points Report](docs/JBPF_HOOK_POINTS_REPORT.md) — 68 jBPF instrumentation points

## Prerequisites

- Ubuntu 22.04+
- srsRAN Project with jBPF hooks
- srsRAN 4G (for srsUE)
- GNU Radio 3.10+ with Python bindings
- InfluxDB 1.6+, Grafana 11+
- Python 3.8+: numpy, scipy, influxdb, protobuf

## License

Internal research project.
