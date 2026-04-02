# srsRAN 5G Telemetry Pipeline

Real-time telemetry collection, channel emulation, and anomaly dataset generation for a 5G NR gNodeB, implemented via eBPF instrumentation (jBPF) over a ZMQ virtual radio interface.

## Overview

This pipeline instruments an srsRAN Project gNB with approximately 60 eBPF codelets across the MAC, RLC, PDCP, FAPI, RRC, and NGAP protocol layers, extracting 17 telemetry schemas without modification to the gNB source code. A custom ZMQ channel broker (available in C and Python/GNU Radio variants) injects calibrated RF impairments -- AWGN, Rician/Rayleigh fading, 3GPP EPA/EVA/ETU frequency-selective fading, carrier frequency offset, burst drops, and CW/narrowband interference -- into the IQ sample stream between the gNB and a software UE. Telemetry is ingested into InfluxDB and visualised on a 39-panel Grafana dashboard with 5-second auto-refresh. An optional real-time QT GUI provides spectrum, constellation, IQ waveform, and waterfall displays with interactive parameter control.

A stress injection framework applies 23 system-level scenarios (CPU, memory, scheduling, traffic, and combined stressors) to generate labelled anomalous datasets suitable for anomaly detection research. A separate realistic channel dataset collector runs 10 real-world-grounded GRC channel scenarios (baselines, time-varying, steady impairment, and RLF cycles), exporting telemetry to CSV and HDF5.

## Architecture

```
gNB (jBPF) --ZMQ--> Channel Broker --ZMQ--> srsUE --> iperf3 UL :5201
    |           (fading + AWGN +                  +-> iperf3 DL :5202 (--reverse)
    |            interference)                    +-> ping RTT -> /tmp/ping_ue.log
    |
    +-- ~60 eBPF codelets -> 17 telemetry schemas
    |
    +-- jrtc -> gRPC Decoder -> /tmp/decoder.log
                                    |
                                    v
                        telemetry_to_influxdb.py -> InfluxDB -> Grafana (39 panels)
```

## Quick Start

```bash
# C broker -- Rician fading (recommended; triggers HARQ failures)
./scripts/launch_mac_telemetry.sh --fading

# GRC Python broker -- EPA frequency-selective fading
./scripts/launch_mac_telemetry.sh --grc --profile epa --snr 28

# GRC broker with live QT GUI (sliders + spectrum/constellation plots)
./scripts/launch_mac_telemetry.sh --gui --fading

# CW interference at 1 MHz offset, SIR = 10 dB
./scripts/launch_mac_telemetry.sh --interference-type cw --sir 10

# Narrowband (1 PRB) interference -- automatically uses GRC broker
./scripts/launch_mac_telemetry.sh --interference-type narrowband --sir 15

# Stop the pipeline
./scripts/stop_mac_telemetry.sh

# Collect stress anomaly dataset (23 scenarios)
./scripts/stress_anomaly_collect.sh --duration 180

# Collect realistic channel dataset (10 scenarios, ~37 min)
./scripts/collect_channel_realistic.sh --duration 180 --output ~/channel_dataset

# Export channel dataset logs to CSV + HDF5
python3 scripts/export_channel_dataset.py ~/channel_dataset
```

The Grafana dashboard is accessible at `http://localhost:3000` (admin / admin).

## Channel Broker Capabilities

| Feature | C Broker | GRC Python Broker |
|---------|:--------:|:-----------------:|
| AWGN | Y | Y |
| Flat Rician / Rayleigh fading | Y | Y |
| 3GPP EPA / EVA / ETU fading | -- | Y |
| Carrier Frequency Offset (CFO) | -- | Y |
| Burst error injection | -- | Y |
| Time-varying scenarios | -- | Y |
| CW tone interference | Y | Y |
| Narrowband (1 PRB) interference | -- | Y |
| Live QT GUI | -- | Y |

## Directory Structure

```
scripts/            Pipeline scripts (launch, stop, brokers, ingestor, plotting,
                    stress anomaly collection)
docs/               Technical documentation
  ZMQ_CHANNEL_BROKER_DOCS.md   Channel broker and channel model reference
  PROJECT_REFERENCE.md         Full project technical reference
  JBPF_HOOK_POINTS_REPORT.md  68 jBPF instrumentation points
  JBPF_MAC_TELEMETRY_PROMPT.md MAC codelet architecture and data formats
  grcParamPreset.md            GRC broker parameter presets and safety guide
codelets/           eBPF codelet sets (11 sets, ~60 programs)
config/             gNB, UE, and broker configuration files
grafana/            Dashboard JSON and provisioning
plots/              Generated telemetry plot PNGs
project_extension/  Stress anomaly extension -- docs, figures, analysis scripts
```

## Documentation

- [Channel Broker Reference](docs/ZMQ_CHANNEL_BROKER_DOCS.md) -- Broker architecture, channel models, interference simulation, measured results, CLI reference, troubleshooting
- [Project Reference](docs/PROJECT_REFERENCE.md) -- System architecture, development phases, telemetry schemas, port map, data quirks, known issues
- [Hook Points Report](docs/JBPF_HOOK_POINTS_REPORT.md) -- Complete inventory of 68 jBPF instrumentation points
- [MAC Telemetry Prompt](docs/JBPF_MAC_TELEMETRY_PROMPT.md) -- MAC codelet architecture, data formats, step-by-step launch guide
- [GRC Parameter Presets](docs/grcParamPreset.md) -- Safe parameter ranges and recommended configurations
- [**Anomaly Dataset Collection**](docs/ANOMALY_DATASET.md) -- Both dataset types: stress anomalies (23 scenarios) and realistic channel scenarios (10 scenarios), per-scenario results, key findings, reproduction steps, dataset structure, and data quirks



## Prerequisites

- Ubuntu 22.04 or later
- srsRAN Project with jBPF hooks
- srsRAN 4G (for srsUE)
- GNU Radio 3.10+ with Python bindings (for the GRC broker)
- InfluxDB 1.6+, Grafana 11+
- Python 3.8+: numpy, scipy, influxdb, protobuf

## License

Internal research project.
