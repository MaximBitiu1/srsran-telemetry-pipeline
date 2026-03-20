# srsRAN 5G NR Telemetry Pipeline — Technical Report

**Author:** Maxim  
**Date:** March 2026  
**Project:** Real-time 5G gNB Telemetry with eBPF Instrumentation and Configurable Channel Emulation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Project Overview](#2-project-overview)
3. [System Architecture](#3-system-architecture)
4. [What Was Built](#4-what-was-built)
5. [GNU Radio Channel Broker — Design Decision](#5-gnu-radio-channel-broker--design-decision)
6. [How the GRC Broker Works](#6-how-the-grc-broker-works)
7. [QT GUI — Real-Time Visualization](#7-qt-gui--real-time-visualization)
8. [Channel Parameters & Dynamic Capabilities](#8-channel-parameters--dynamic-capabilities)
9. [Telemetry Schemas & Grafana Dashboard](#9-telemetry-schemas--grafana-dashboard)
10. [File Inventory](#10-file-inventory)
11. [How to Run](#11-how-to-run)
12. [Results & Validation](#12-results--validation)

---

## 1. Executive Summary

We built an **end-to-end real-time telemetry pipeline** for a 5G NR gNodeB (gNB) running on srsRAN Project. The pipeline uses **eBPF-based instrumentation** (jBPF) to extract 17 distinct telemetry schemas from the gNB's MAC, RLC, PDCP, FAPI, RRC, and NGAP layers — all **without modifying the gNB source code**. Telemetry data flows through a gRPC decoder into InfluxDB and is visualized in a 39-panel Grafana dashboard with 5-second refresh.

To create realistic and *controllable* radio channel conditions, we developed a **GNU Radio Python Channel Broker** (`srsran_channel_broker.py`, 950 lines) that sits between the gNB and UE in the ZMQ-based IQ sample pipeline. This broker supports:

- **AWGN** (Additive White Gaussian Noise)
- **Flat Rician/Rayleigh fading** (AR1 Jake's Bessel model)
- **Frequency-selective fading** (3GPP EPA, EVA, ETU multi-tap FIR profiles)
- **Carrier Frequency Offset (CFO)** injection
- **Burst error injection** (random subframe drops)
- **Time-varying scenarios** (Drive-by, Urban Walk, Edge-of-cell)
- **Live QT GUI** with interactive sliders and 4 real-time signal plots

The entire pipeline — from jrtc, gNB, UE, channel broker, decoder, codelets, Grafana, and InfluxDB — launches with a **single command** and tears down cleanly.

---

## 2. Project Overview

### Problem Statement

srsRAN Project provides a software-defined 5G gNB that uses ZMQ sockets for IQ sample transport in simulation mode. By default, the ZMQ link is an ideal point-to-point connection with **no channel impairments** — the signal arrives at the UE exactly as transmitted. This makes the telemetry data unrealistically flat: CRC pass rate is always 100%, HARQ retransmissions are zero, SINR is constant, and throughput never varies.

For meaningful telemetry analysis, anomaly detection research, and AI/ML training, we need:
1. **Realistic channel conditions** — fading, noise, frequency offsets
2. **Controllable impairments** — adjustable parameters for repeatable experiments
3. **Real-time observability** — live visualization of what the channel is doing
4. **Non-intrusive instrumentation** — extract telemetry without modifying the gNB

### Solution

We developed a three-part solution:

1. **jBPF eBPF Codelets** (~60 eBPF programs across 11 codelet sets) — hook into 68 instrumentation points inside the gNB to extract telemetry at MAC, RLC, PDCP, FAPI, RRC, and NGAP layers
2. **GNU Radio Python Channel Broker** — intercepts ZMQ IQ samples between gNB and UE, applies configurable impairments, and provides real-time visualization
3. **Grafana + InfluxDB Dashboard** — 39-panel dashboard showing all 17 telemetry schemas in real-time with 5-second refresh

---

## 3. System Architecture

```
┌─────────┐    ZMQ:4000/4001    ┌─────────────────┐    ZMQ:2000/2001    ┌─────────┐
│         │ ──── DL IQ ───────> │   GRC Channel    │ ──── DL IQ ───────>│         │
│   gNB   │                    │     Broker        │                    │  srsUE  │
│ (jBPF)  │ <─── UL IQ ─────── │  (Python/GR)     │ <─── UL IQ ──────  │ (netns) │
└────┬────┘                    │                   │                    └────┬────┘
     │                         │  ┌─────────────┐  │                         │
     │ jBPF hooks              │  │ QT GUI:     │  │                         │
     │ (68 points)             │  │ • Spectrum   │  │                    iperf3 UDP
     ▼                         │  │ • Time IQ    │  │                    10 Mbps UL
┌─────────┐                    │  │ • Constell.  │  │
│  jrtc   │                    │  │ • Waterfall  │  │
│ runtime │                    │  │              │  │
│ (K8s)   │                    │  │ Sliders:     │  │
└────┬────┘                    │  │ SNR, K, fd   │  │
     │ gRPC (port 20789)       │  │ CFO, Drops   │  │
     ▼                         │  │ Fading Mode  │  │
┌─────────┐                    │  │ Scenario     │  │
│ Decoder │                    │  └─────────────┘  │
│ (srsRAN)│                    └───────────────────┘
└────┬────┘
     │ JSON log (/tmp/decoder.log)
     ▼
┌─────────────┐     InfluxDB queries      ┌─────────────┐
│ Ingestor    │ ──────────────────────────>│  InfluxDB   │
│ (Python)    │     15 measurements       │  (port 8086)│
└─────────────┘                           └──────┬──────┘
                                                  │
                                          ┌───────▼───────┐
                                          │   Grafana     │
                                          │  (port 3000)  │
                                          │  39 panels    │
                                          └───────────────┘
```

### Data Flow

1. **gNB** transmits DL IQ samples via ZMQ REQ to port 4000
2. **GRC Broker** receives the IQ, applies impairments (fading + AWGN + CFO + drops), forwards to UE on port 2000
3. **srsUE** receives impaired DL, transmits UL IQ to the broker on port 2001
4. **GRC Broker** applies UL impairments (flat Rician only — to preserve PUCCH decoding), forwards to gNB on port 4001
5. **jBPF hooks** inside the gNB fire on MAC scheduling, CRC indication, HARQ feedback, RLC TX/RX, PDCP PDUs, RRC procedures, NGAP procedures, and FAPI interfaces
6. **eBPF codelets** aggregate statistics per-UE and emit protobuf-encoded telemetry via shared memory to jrtc
7. **jrtc** forwards telemetry via gRPC to the **decoder**
8. **Decoder** deserializes protobuf and writes JSON records to `/tmp/decoder.log`
9. **Ingestor** (`telemetry_to_influxdb.py`) tails the log, parses each JSON record, maps it to one of 15 InfluxDB measurements, and batch-writes to InfluxDB
10. **Grafana** queries InfluxDB every 5 seconds and renders 39 panels

---

## 4. What Was Built

The project was developed across 10 phases:

| Phase | Description | Key Deliverables |
|:-----:|-------------|------------------|
| 1 | Initial MAC codelet investigation | Identified 10 broken MAC codelets, documented 68 jBPF hook points |
| 2 | MAC codelet fixes | Fixed all 10 MAC codelets (wrong schema fields, buffer overflows, missing maps) |
| 3 | jrtc-ctl bug fixes | Fixed 2 bugs in the codelet loading tool (YAML parsing, path resolution) |
| 4 | Expanded to 10+ codelet sets | Enabled RLC, PDCP, FAPI, RRC, NGAP, perf codelets (11 sets, ~60 codelets) |
| 5 | C ZMQ Channel Broker | Built 477-line C broker with AWGN + Rician/Rayleigh flat fading |
| 6 | Launch/Stop scripts | One-command pipeline launcher (520+ lines) and teardown script |
| 7 | Grafana + InfluxDB pipeline | 616-line Python ingestor, 39-panel dashboard, 15 InfluxDB measurements |
| 8 | Plotting & data validation | 15 PNG telemetry plots, variance analysis across all 17 schemas |
| 9 | HARQ parameter tuning | Systematic SNR/K-factor/Doppler exploration, established stable operating regions |
| 10 | **GNU Radio Python Broker** | 950-line Python GRC broker with 5 new capabilities beyond the C broker |

### Components Built

| Component | Language | Lines | Description |
|-----------|----------|------:|-------------|
| `srsran_channel_broker.py` | Python | 950 | GRC channel broker with EPA/EVA/ETU, CFO, drops, scenarios, QT GUI |
| `zmq_channel_broker.c` | C | 477 | Original lightweight AWGN + flat fading broker |
| `launch_mac_telemetry.sh` | Bash | 520+ | One-command pipeline launcher with 15+ configurable flags |
| `stop_mac_telemetry.sh` | Bash | 105 | Clean teardown (reverse order, process verification) |
| `telemetry_to_influxdb.py` | Python | 616 | Decoder log → InfluxDB ingestor (15 measurements, live/replay modes) |
| `plot_all_telemetry.py` | Python | 944 | Generates 15 PNG telemetry plots from InfluxDB |
| `collect_anomalous_data.sh` | Bash | 260 | Automated dataset collection under varying channel conditions |
| 10 codelet sets | C/eBPF | ~3000 | 60 eBPF programs across MAC, RLC, PDCP, FAPI, RRC, NGAP, perf |
| Grafana dashboard | JSON | 2000+ | 39 panels across 8 sections with auto-refresh |

---

## 5. GNU Radio Channel Broker — Design Decision

### Why Not Use the Existing GNU Radio Companion (GRC)?

GNU Radio Companion (GRC) is the standard graphical tool for building GNU Radio flowgraphs. It generates Python code from a visual block diagram. We considered using it but chose to write the broker as a **standalone Python script** instead. Here is why:

#### 1. GRC Cannot Express Custom ZMQ REQ/REP Relay Logic

The core of our broker is a **ZMQ REQ/REP relay** — it receives IQ samples from the gNB's ZMQ REQ socket, applies impairments, and forwards them to the UE's ZMQ REP socket. The standard GNU Radio ZMQ blocks (`ZMQ REQ Source`, `ZMQ REP Sink`) are designed for simple streaming scenarios. They do **not** support the bidirectional request/reply pattern that srsRAN's ZMQ interface requires:

- The gNB sends an IQ buffer on its TX port and **waits** for a response on its RX port
- The UE does the same in the opposite direction
- The broker must act as both REP server (to the gNB/UE) and REQ client (to the other end) — simultaneously on 4 ports

This relay pattern requires **custom socket management** with careful timeout handling, which cannot be expressed as a standard GRC block connection.

#### 2. Embedded Python Blocks in GRC Are Limited

GRC supports "Embedded Python Blocks" for custom processing, but they operate within GRC's stream-based scheduler. Our broker needs to:

- Run two independent relay threads (DL and UL) with different impairment chains
- Apply impairments **per-message** (not per-sample stream), since each ZMQ message is a complete subframe (23,040 samples)
- Share mutable state between the relay threads and the GUI (for live parameter adjustment)
- Handle ZMQ socket timeouts and error recovery

These requirements are easier to implement correctly in a standalone Python class than within GRC's embedded block constraints.

#### 3. Headless Mode for Automated Pipelines

The launch script needs to start the broker **headless** (without a GUI) in production/CI pipelines. GRC-generated flowgraphs are tightly coupled to the QT GUI — disabling the GUI requires modifying the generated code. Our standalone script has a clean `--no-gui` flag that uses a completely separate `HeadlessBroker` class, avoiding all QT dependencies.

#### 4. 3GPP Fading Models Require Custom DSP

The frequency-selective fading models (EPA, EVA, ETU) use multi-tap FIR filters with per-tap AR(1) fading processes. Each tap has its own delay, power, and independently correlated fading coefficient. This requires:

- Custom `FrequencySelectiveFading` class with scipy's `lfilter` for FIR convolution
- Per-tap `FadingState` objects with the Jake's Bessel autocorrelation model
- Tap delay quantization to the sample rate (23.04 MHz → 43.4 ns per sample)

GNU Radio has a built-in fading model block (`gr::channels::fading_model`), but it does not support the 3GPP EPA/EVA/ETU delay profiles directly, and integrating it with our ZMQ relay pattern would require significant workaround code.

#### 5. Reproducibility and Portability

A standalone `.py` file is:
- **Self-contained** — no `.grc` XML file needed, no GRC installation required beyond `gnuradio` Python packages
- **Version-controllable** — clean diff history in git
- **Portable** — runs on any system with Python 3 and GNU Radio 3.10+
- **Modifiable** — parameters, fading models, and scenarios can be changed by editing one file

### What We Still Use from GNU Radio

Even though we don't use GRC's graphical editor, we **do** use GNU Radio's runtime and QT GUI modules:

| GNU Radio Component | How We Use It |
|---------------------|---------------|
| `gnuradio.gr` | Base classes for `gr.top_block` and `gr.sync_block` — our broker source block inherits from these |
| `gnuradio.qtgui` | Frequency sink, time sink, constellation sink, waterfall sink — real-time signal visualization |
| `gnuradio.blocks` | Throttle block — rate-limits the visualization pipeline to the sample rate |
| `gnuradio.filter` | FIR design utilities (used for window functions in FFT-based visualizations) |

So the broker is best described as: **a GNU Radio Python application that uses GR's runtime and QT GUI visualization, but with custom ZMQ relay logic and DSP that cannot be expressed in GRC's graphical editor.**

---

## 6. How the GRC Broker Works

### Signal Processing Chain

Each IQ subframe (23,040 complex samples at 23.04 MHz, = 1 ms) passes through the following impairment chain:

```
           gNB TX (port 4000)
               │
               ▼
    ┌──────────────────────┐
    │  1. Burst Drop Check │  randomly zero entire subframe
    │     (probability p)  │  with probability p (0–25%)
    └──────────┬───────────┘
               │
    ┌──────────▼───────────┐
    │  2. Fading            │  multiply by complex channel
    │     • Flat Rician     │  coefficient h[n]:
    │     • Flat Rayleigh   │    h = LOS + scatter·(hI + jhQ)
    │     • EPA 7-tap FIR   │  or convolve with multi-tap
    │     • EVA 9-tap FIR   │  FIR: y[n] = Σ h_k[n]·x[n-τ_k]
    │     • ETU 9-tap FIR   │
    └──────────┬───────────┘
               │
    ┌──────────▼───────────┐
    │  3. CFO Injection     │  x'[n] = x[n] · e^(j2π·Δf·n/fs)
    │     (Hz offset)       │  cumulative phase across frames
    └──────────┬───────────┘
               │
    ┌──────────▼───────────┐
    │  4. AWGN Addition     │  x''[n] = x'[n] + noise
    │     (SNR-based)       │  σ = √(P_signal / SNR_linear)
    └──────────┬───────────┘
               │
               ▼
           UE RX (port 2000)
```

### Fading Model Details

#### Flat Fading (AR1 Jake's Bessel Model)

For flat fading modes (Rician and Rayleigh), each sample's channel coefficient is generated by an **AR(1) process** with the **Jake's Bessel autocorrelation**:

$$h[n+1] = \alpha \cdot h[n] + \sigma_w \cdot w[n]$$

where:
- $\alpha = J_0(2\pi f_d / f_s)$ is the AR(1) coefficient using the zeroth-order Bessel function of the first kind
- $f_d$ is the maximum Doppler frequency (Hz)
- $f_s$ is the sample rate (23.04 MHz)
- $w[n]$ is i.i.d. complex Gaussian noise
- The I and Q components are generated independently

For **Rician fading** with K-factor $K$ (linear):

$$h_{total} = \sqrt{\frac{K}{K+1}} + \sqrt{\frac{1}{K+1}} \cdot h_{scatter}$$

where the first term is the constant LOS (line-of-sight) component and the second is the scatter component.

For **Rayleigh fading**, $K = 0$, so there is no LOS component — the channel can fade to near-zero, causing deep nulls.

#### Frequency-Selective Fading (3GPP EPA/EVA/ETU)

For frequency-selective modes, the channel is modeled as a **tapped delay line** (FIR filter) where each tap has:
- A fixed delay $\tau_k$ (quantized to the sample rate)
- A fixed average power $P_k$ (from the 3GPP tables)
- An independent time-varying fading coefficient $h_k[n]$ generated by the AR(1) Jake's model

The channel output is:

$$y[n] = \sum_{k=0}^{L-1} h_k[n] \cdot \sqrt{P_k} \cdot x[n - \tau_k]$$

| Profile | Taps | Max Delay | Typical Use Case |
|---------|-----:|-----------|------------------|
| EPA | 7 | 410 ns | Extended Pedestrian A — mild ISI |
| EVA | 9 | 2,510 ns | Extended Vehicular A — moderate ISI |
| ETU | 9 | 5,000 ns | Extended Typical Urban — severe ISI |

### UL vs DL Asymmetry

The UL path uses **flat Rician fading only** (even if DL uses EPA/EVA/ETU), because:
- Frequency-selective fading on the UL causes PUCCH decoding failures, which lose the scheduling feedback loop
- UL SINR is critical for the gNB's scheduler to maintain the connection
- The DL is where we want to stress-test the equalizer and observe telemetry variations

### ZMQ Relay Architecture

The broker uses **two independent relay threads** — one for DL and one for UL — running in parallel:

```python
# DL thread: gNB TX (REQ:4000) → Broker → UE RX (REP:2000)
# UL thread: UE TX (REQ:2001) → Broker → gNB RX (REP:4001)
```

Each thread follows the ZMQ REQ/REP protocol:
1. Wait for a REQ from the downstream side (UE or gNB)
2. Forward the request to the upstream side
3. Receive the IQ response
4. Apply impairments to the IQ samples
5. Send the impaired IQ back to the requester

This relay pattern is **transparent** to both the gNB and UE — they believe they are connected directly.

---

## 7. QT GUI — Real-Time Visualization

When launched with `--gui`, the broker displays a **QT window with 4 real-time signal plots and 7 interactive controls**:

### Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│                    srsRAN 5G NR Channel Broker                      │
├──────────────────────────┬──────────────────────────────────────────┤
│  Row 0:                  │                                          │
│  [ SNR (dB) ═══●═══ ]   │  [ K-Factor (dB) ═══●═══ ]             │
│    5 ← 28.0 → 40        │    -10 ← 3.0 → 20                      │
├──────────────────────────┼──────────────────────────────────────────┤
│  Row 1:                  │                                          │
│  [ Doppler (Hz) ═●═ ]   │  [ Fading Mode ▼ ]                      │
│    0.1 ← 5.0 → 300      │    Flat Rician / Rayleigh / EPA/EVA/ETU │
├────────────┬─────────────┼──────────────────────────────────────────┤
│  Row 2:    │             │                                          │
│  CFO (Hz)  │ Drop Prob   │  [ Scenario ▼ ]                         │
│  -500→500  │  0→0.25     │    Manual / Drive-by / Urban / Edge     │
├────────────┴─────────────┼──────────────────────────────────────────┤
│                          │                                          │
│   DL Channel Spectrum    │   DL IQ Waveform                        │
│   (Frequency Domain)     │   (Time Domain)                         │
│                          │                                          │
│   2048-pt FFT            │   I (blue) and Q (red) traces           │
│   Blackman-Harris window │   Autoscaled amplitude                  │
│   -80 to +10 dB range    │   2048 samples per update               │
│   23.04 MHz bandwidth    │   100 ms update rate                    │
│                          │                                          │
├──────────────────────────┼──────────────────────────────────────────┤
│                          │                                          │
│   DL Constellation       │   DL Waterfall                          │
│   (IQ Scatter Plot)      │   (Spectrogram)                         │
│                          │                                          │
│   Complex I vs Q plane   │   Frequency vs Time vs Power            │
│   Shows modulation       │   Color: -80 to +10 dB                 │
│   quality and fading     │   Shows spectral evolution              │
│   effects                │   over time                             │
│                          │                                          │
└──────────────────────────┴──────────────────────────────────────────┘
```

### What Each Plot Shows

| Plot | What It Shows | What to Look For |
|------|---------------|------------------|
| **DL Channel Spectrum** | Power spectral density of the DL IQ after impairments (2048-point FFT with Blackman-Harris window). X-axis: frequency (-11.52 to +11.52 MHz), Y-axis: power (dB). | Under AWGN-only, the spectrum is flat. Under frequency-selective fading (EPA/EVA/ETU), you see frequency-selective notches where certain subcarriers are attenuated. Under CFO, the entire spectrum shifts left/right. |
| **DL IQ Waveform** | Real-time time-domain trace of I (blue) and Q (red) components. Shows 2048 samples (~89 µs) per update. | Under Rician fading, the envelope varies slowly (at Doppler rate). Under burst drops, the signal goes to zero for entire subframes. CFO causes the I/Q waveform to rotate, creating a beating pattern. |
| **DL Constellation** | Scatter plot of complex IQ samples (I on X-axis, Q on Y-axis). | Clean constellation shows tight clusters (good SNR). With fading, the constellation smears radially (amplitude variation) and/or rotationally (phase variation). With CFO, the constellation rotates in a circle. |
| **DL Waterfall** | Spectrogram showing how the spectrum evolves over time. X-axis: frequency, Y-axis: time (scrolling), Color: power (dB). | Shows time-varying channels clearly — you can see the fading come and go as colored bands. EPA/EVA/ETU show frequency-selective patterns evolving over time at the Doppler rate. |

### Interactive Controls

All controls modify parameters **in real-time** — the changes take effect on the next ZMQ message (within 1 ms):

| Control | Type | Range | Effect |
|---------|------|-------|--------|
| **SNR (dB)** | Slider | 5 – 40 dB | Controls AWGN noise power. Lower SNR = more noise = lower CRC pass rate |
| **K-Factor (dB)** | Slider | -10 – 20 dB | Rician K-factor. Higher = stronger LOS = less fading variation. 0 dB = equal LOS and scatter. Negative = Rayleigh-like |
| **Doppler (Hz)** | Slider | 0.1 – 300 Hz | Controls fading speed. 5 Hz ≈ pedestrian, 70 Hz ≈ vehicular, 300 Hz ≈ high-speed train |
| **Fading Mode** | Dropdown | 6 options | Off (AWGN), Flat Rician, Flat Rayleigh, EPA, EVA, ETU |
| **CFO (Hz)** | Slider | -500 – +500 Hz | Carrier frequency offset. Stresses the UE's frequency synchronization tracking |
| **Drop Prob** | Slider | 0 – 0.25 | Probability of dropping (zeroing) an entire subframe. Simulates deep fades or interference |
| **Scenario** | Dropdown | 4 options | Manual, Drive-by (30s sinusoidal cycle), Urban Walk (random perturbations), Edge of Cell (60s linear decline) |

---

## 8. Channel Parameters & Dynamic Capabilities

### Parameter Reference

| Parameter | CLI Flag | Default | Range | Effect on Telemetry |
|-----------|----------|---------|-------|---------------------|
| SNR | `--snr` | 28 dB | 5–40 dB | Primary control. ≤20 dB → CRC failures, HARQ retransmissions. ≤15 dB → UE detach risk |
| K-Factor | `--k-factor` | 3 dB | -10–20 dB | Controls fading depth. K=3 dB is mild (LOS dominant). K=0 dB is severe (equal LOS/scatter). K<0 dB is Rayleigh-like |
| Doppler | `--doppler` | 5 Hz | 0.1–300 Hz | Controls fading rate. Higher = faster SINR variation = more HARQ/CRC variance in telemetry |
| Fading Profile | `--profile` | flat | flat/epa/eva/etu | flat = single-tap multiplicative fading. EPA/EVA/ETU = multi-tap FIR → inter-symbol interference |
| CFO | `--cfo` | 0 Hz | -500–500 Hz | Frequency offset causes phase drift. >100 Hz may cause sync loss. Visible in PDCCH/PUCCH metrics |
| Drop Probability | `--drop-prob` | 0 | 0–0.25 | Random IQ zeroing. >5% causes significant HARQ increase. >10% causes RLC retransmissions |
| Scenario | `--scenario` | none | none/drive-by/urban-walk/edge-of-cell | Auto-varies parameters over time for dynamic telemetry diversity |
| Rayleigh shortcut | `--rayleigh` | off | flag | Forces K = -100 dB (pure Rayleigh, deep fades). Unstable above fd=10 Hz |

### Stability Tiers

Based on extensive testing, we established these stability tiers:

#### Tier 1 — Rock Solid (runs indefinitely)
```bash
--snr 28 --k-factor 3 --doppler 5                  # Current default
--snr 30 --k-factor 6 --doppler 5                  # Strong LOS, very clean
--snr 25 --k-factor 3 --doppler 5 --cfo 30         # With mild CFO
```
- SINR: 25–42 dB
- CRC pass rate: >99%
- HARQ NACK rate: <2%
- Telemetry variation: Low — mostly flat with small fluctuations

#### Tier 2 — Stable with Visible Dynamics (10–30 minutes)
```bash
--snr 22 --k-factor 1 --doppler 10                 # Weaker LOS, faster fading
--snr 25 --k-factor 3 --doppler 10 --cfo 50        # Moderate walking
--snr 25 --k-factor 3 --doppler 5 --scenario urban-walk  # Auto-varying
```
- SINR: 18–35 dB (varies)
- CRC pass rate: 95–99%
- HARQ NACK rate: 2–10%
- Telemetry variation: **Good for analysis** — clear fading-correlated patterns

#### Tier 3 — Dynamic/Stress Test (3–10 minutes before UE detach)
```bash
--snr 20 --k-factor 0 --doppler 10                 # Deep fades possible
--snr 22 --drop-prob 0.03                           # 3% burst drops
--snr 22 --scenario edge-of-cell                   # Declining SNR to 8 dB
```
- SINR: 10–25 dB (high variance)
- CRC pass rate: 80–95%
- HARQ NACK rate: 10–30%
- Telemetry variation: **High** — good for anomaly detection training

#### Tier 4 — Extreme (UE drops within 1–3 minutes)
```bash
--rayleigh --doppler 20                             # Fast Rayleigh
--snr 15 --k-factor 0 --doppler 10                 # Low SNR + deep fades
--drop-prob 0.10                                    # 10% drops
```
- UE cannot sustain connection
- Useful for: testing RRC re-establishment, NGAP release procedures

### Scenario Descriptions

| Scenario | Duration | Parameter Trajectory | Use Case |
|----------|----------|---------------------|----------|
| **Drive-by** | 30s cycle (repeats) | SNR: 30→15→30 dB (sinusoidal), Doppler: 5→200→5 Hz, Drops: 0→2%→0 | Simulates a vehicle driving past the cell, creating a symmetric fade-and-recover pattern |
| **Urban Walk** | Continuous (random) | SNR: bounded random walk (12–35 dB), Doppler: bounded walk (1–20 Hz), Drops: 5% bursts with 15% probability each second | Simulates a pedestrian in an urban environment with random signal variations, occasional blockage |
| **Edge of Cell** | 60s ramp (one-shot) | SNR: 30→8 dB (linear decline), Drops: 0→10% (linear increase) | Simulates walking away from the cell site toward the cell edge, ending in disconnection |

---

## 9. Telemetry Schemas & Grafana Dashboard

### 17 Telemetry Schemas

The eBPF codelets extract 17 distinct telemetry schemas from the gNB:

| # | Schema | Layer | Type | Key Fields |
|---|--------|-------|------|------------|
| 1 | `mac_crc_stats` | MAC | Periodic | avg_sinr, crc_pass/fail, avg_mcs, avg_ri, num_crc |
| 2 | `mac_bsr_stats` | MAC | Periodic | avg_bsr_lcg0–3, num_bsr |
| 3 | `mac_uci_stats` | MAC | Periodic | sr_count, csi_count, harq_ack_count |
| 4 | `mac_dl_harq_stats` | MAC | Periodic | total_acks, total_nacks, total_dtx, retx count, max_retx |
| 5 | `mac_ul_harq_stats` | MAC | Periodic | total_acks, total_nacks, total_crc_fail, retx count |
| 6 | `rlc_dl_stats` | RLC | Periodic | tx_pdus, tx_bytes, retx_pdus, retx_bytes |
| 7 | `rlc_ul_stats` | RLC | Periodic | rx_pdus, rx_bytes, rx_delivered |
| 8 | `pdcp_dl_stats` | PDCP | Periodic | tx_data_pdus, tx_ctrl_pdus, tx_bytes, discard_count |
| 9 | `pdcp_ul_stats` | PDCP | Periodic | rx_data_pdus, rx_ctrl_pdus, rx_bytes, delivered_sdus |
| 10 | `fapi_dl_config_stats` | FAPI | Periodic | num_pdcch_pdus, num_pdsch_pdus, num_ssb_pdus |
| 11 | `fapi_ul_config_stats` | FAPI | Periodic | num_pucch_pdus, num_pusch_pdus, num_prach_pdus |
| 12 | `fapi_crc_stats` | FAPI | Periodic | num_crcs, avg_sinr, avg_ta |
| 13 | `fapi_rach_stats` | FAPI | Event | num_preambles, avg_ta, avg_snr |
| 14 | `rrc_ue_*` | RRC | Event | ue_index, c_rnti, procedure_name, result |
| 15 | `ngap_*` | NGAP | Event | procedure_name, success/failure, duration |
| 16 | `ue_context_*` | DU | Event | du_ue_index, creation/deletion/update timestamps |
| 17 | `jbpf_perf` | jBPF | Periodic | codelet execution times, hook latencies |

### Grafana Dashboard — 39 Panels

The dashboard (UID: `srsran-5g-nr-telemetry`) is organized into 8 sections:

| Section | Panels | Key Metrics Visualized |
|---------|:------:|------------------------|
| **SINR & CRC** | 6 | SINR time series, CRC pass/fail rate, MCS distribution, rank indicator |
| **HARQ** | 6 | DL ACK/NACK/DTX, UL ACK/NACK/CRC-fail, retransmission counts, max retx |
| **BSR & UCI** | 4 | Buffer Status Reports per LCG, SR count, CSI count, HARQ-ACK count |
| **RLC** | 6 | DL TX/retx PDUs, DL TX bytes, UL RX PDUs, UL delivered bytes |
| **PDCP** | 6 | DL data/ctrl PDUs, DL discard count, UL data PDUs, UL delivered SDUs |
| **FAPI** | 4 | DL/UL config PDU counts, CRC SINR, timing advance, RACH events |
| **RRC/NGAP** | 4 | UE lifecycle events (add/remove/update), RRC procedures, NGAP procedures |
| **jBPF Performance** | 3 | Codelet execution times, hook call latencies, overhead metrics |

---

## 10. File Inventory

### Core Pipeline Files

| File | Size | Purpose |
|------|------|---------|
| `srsran_channel_broker.py` | 950 lines | GNU Radio Python channel broker (main broker) |
| `zmq_channel_broker.c` | 477 lines | Original C broker (simpler, lower overhead) |
| `launch_mac_telemetry.sh` | 520+ lines | One-command pipeline launcher |
| `stop_mac_telemetry.sh` | 105 lines | Clean pipeline teardown |
| `telemetry_to_influxdb.py` | 616 lines | InfluxDB ingestor |
| `plot_all_telemetry.py` | 944 lines | Telemetry plot generator |
| `collect_anomalous_data.sh` | 260 lines | Automated dataset collection |
| `ue_zmq.conf` | 57 lines | srsUE configuration |
| `gnb_zmq.yaml` | ~100 lines | gNB configuration reference |

### Documentation

| File | Purpose |
|------|---------|
| `SUPERVISOR_REPORT.md` | This document |
| `ZMQ_CHANNEL_BROKER_DOCS.md` | Detailed channel broker documentation |
| `AI_CONTINUATION_PROMPT.md` | AI session handoff document |
| `JBPF_MAC_TELEMETRY_PROMPT.md` | Original architecture specification |
| `JBPF_HOOK_POINTS_REPORT.md` | Complete inventory of 68 jBPF hook points |
| `PROJECT_SUMMARY.txt` | Concise project summary |

### Key Directories

| Directory | Contents |
|-----------|----------|
| `jrtc-apps/codelets/` | 11 codelet sets (10 active), ~60 eBPF programs |
| `srsRAN_Project_jbpf/` | 5G gNB with jBPF hooks (forked srsRAN Project) |
| `srsRAN_4G/` | srsUE source (4G project, provides UE binary) |
| `jrt-controller/` | jBPF runtime controller (Go, K8s-based) |
| `grafana/` | Grafana 11.5.2 + provisioned dashboard + datasource |
| `plots/` | 15 PNG telemetry visualization plots |
| `dataset/` | Collected telemetry datasets |

---

## 11. How to Run

### Prerequisites

- Ubuntu 22.04+ with sudo access
- srsRAN Project with jBPF (pre-built in `srsRAN_Project_jbpf/`)
- srsRAN 4G (for srsUE, pre-built in `srsRAN_4G/`)
- GNU Radio 3.10+ with Python bindings
- InfluxDB 1.6+ (systemd service)
- Grafana 11+ (standalone, in `grafana/`)
- Python 3.8+ with: numpy, scipy, influxdb, protobuf, packaging
- Docker (for K3d/jrtc runtime)

### Launch the Full Pipeline

```bash
# Basic launch (AWGN only, no fading)
~/Desktop/launch_mac_telemetry.sh

# With GRC broker and Rician fading
~/Desktop/launch_mac_telemetry.sh --grc --fading --snr 28 --k-factor 3 --doppler 5

# With GUI (interactive mode)
~/Desktop/launch_mac_telemetry.sh --grc --fading --gui --snr 25 --k-factor 1 --doppler 10

# With time-varying scenario
~/Desktop/launch_mac_telemetry.sh --grc --fading --snr 28 --scenario urban-walk

# With frequency-selective fading (EPA profile)
~/Desktop/launch_mac_telemetry.sh --grc --fading --profile epa --doppler 5

# Stop everything
~/Desktop/stop_mac_telemetry.sh
```

### Access the Dashboard

Open `http://localhost:3000` in a browser. Login: `admin` / `admin`. The dashboard auto-refreshes every 5 seconds.

---

## 12. Results & Validation

### Data Validation Summary

With the pipeline running at `--snr 28 --k-factor 3 --doppler 5`:

| Metric | Observed Value | Expected | Status |
|--------|:-----------:|:--------:|:------:|
| PHY SINR | 26–42 dB | ~28 dB ± fading | ✓ |
| CRC Pass Rate | >99% | High at SNR=28 | ✓ |
| DL HARQ ACK Rate | >98% | High at SNR=28 | ✓ |
| UL HARQ ACK Rate | >97% | High at SNR=28 | ✓ |
| MCS | 27 (64QAM) | Max MCS at high SINR | ✓ |
| RLC DL TX | ~500 PDU/s | Active traffic | ✓ |
| iperf3 UL throughput | 10 Mbps | Matches config | ✓ |
| Data points in Grafana | 31+ per 5 min | Continuous flow | ✓ |
| Codelet sets loaded | 11/11 | All active | ✓ |
| Telemetry schemas active | 17/17 | Full coverage | ✓ |

### Key Findings

1. **The GRC broker does NOT cause pipeline instability.** All crashes were traced to an iperf3 race condition where the traffic generator started before the UE's TUN interface was ready. This caused a `BearerContextInactivityNotification` after ~2 minutes of no data-plane traffic, leading to a clean UE release. The fix (waiting for TUN interface readiness) resolved the issue completely.

2. **SINR at PHY is consistently higher than configured SNR** (e.g., 42 dB PHY SINR at 28 dB configured SNR). This is expected because the gNB's beamforming and receiver processing gain add ~10–14 dB to the raw channel SNR.

3. **UL uses milder fading than DL** by design. Frequency-selective fading on the UL path causes PUCCH decoding failures, which breaks the scheduling feedback loop. The UL always uses flat Rician fading regardless of the DL profile setting.

4. **The "trap invalid opcode" in dmesg** is a known issue in the gNB binary (likely compiled with CPU instructions not supported by this hardware). It occurs only during process exit (47 seconds after clean shutdown) and has no impact on operation.

---

*End of Report*
