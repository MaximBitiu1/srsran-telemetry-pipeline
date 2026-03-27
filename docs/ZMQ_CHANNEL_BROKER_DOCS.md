# ZMQ Channel Broker -- RF Impairment Simulation for srsRAN ZMQ Radio

## 1. Overview

The ZMQ Channel Broker is a custom IQ-level noise injection and fading tool for the srsRAN 5G NR ZMQ-based simulation environment. Two implementations are provided: a C broker supporting AWGN, Rician/Rayleigh flat fading, and CW interference; and a Python/GNU Radio (GRC) broker that extends these capabilities with 3GPP frequency-selective fading (EPA/EVA/ETU), carrier frequency offset, burst error injection, narrowband interference, time-varying scenarios, and a live QT GUI.

### 1.1 Problem Statement

The srsRAN 5G stack uses ZMQ virtual radio to connect gNB and srsUE without physical RF hardware. By default, this creates a perfect channel (zero noise, zero fading, zero delay), yielding unrealistically constant telemetry:

| Metric (Perfect Channel) | Value |
|---|---|
| SINR | 42--43 dB (constant) |
| CQI | 15 (maximum, constant) |
| DL MCS | 27--28 (maximum) |
| UL MCS | 28 (maximum, constant) |
| HARQ retransmissions | 0 |
| HARQ failures | 0 |

The broker introduces calibrated channel impairments so that MAC scheduler telemetry reflects realistic conditions: MCS adaptation, HARQ retransmissions, SINR variation, and buffer dynamics.

### 1.2 Design Rationale

Three approaches to channel impairment were evaluated:

1. **srsUE built-in channel emulator** -- The srsRAN 4G channel emulator (`[channel.dl]`/`[channel.ul]` config sections) supports AWGN and EPA/EVA/ETU fading, but inspection of the source code confirmed that it is wired into the LTE PHY path only (`srsue/src/phy/sync.cc`). The NR PHY path (`srsue/src/phy/nr/`) contains zero references to the channel emulator. In an NR-only configuration, the channel sections are parsed but silently ignored. This approach was not viable without patching the NR PHY.

2. **Patching srsRAN NR PHY** -- Integrating the `srsran_channel_t` struct into the NR sample processing pipeline would enable all channel models natively but would require invasive modifications to the NR PHY code, ongoing maintenance, and risk of introducing subtle PHY bugs.

3. **ZMQ Channel Broker (chosen)** -- A standalone process intercepting IQ samples at the ZMQ transport layer. This approach requires zero modifications to srsRAN source code, works at the IQ level (affecting all physical layer processing), and provides maximum observable change across all telemetry codelets with minimum implementation complexity. Fading was initially implemented as Rayleigh, then converted to Rician after pure Rayleigh caused connection crashes within 1--3 minutes due to complete channel nulls. The GRC Python broker was subsequently developed to provide frequency-selective fading, which the C broker cannot efficiently implement (FFT-based multi-tap filtering).

---

## 2. Architecture

### 2.1 Port Topology

```
Original (perfect channel):
  gNB TX -> :2000 (REP) <- UE RX (REQ)
  UE  TX -> :2001 (REP) <- gNB RX (REQ)

With broker (impaired channel):
  gNB TX -> :4000 (REP) <- Broker DL (REQ) -> [Impairments] -> :2000 (REP) <- UE RX (REQ)
  UE  TX -> :2001 (REP) <- Broker UL (REQ) -> [Impairments] -> :4001 (REP) <- gNB RX (REQ)
```

The gNB config (`gnb_zmq_jbpf.yml`) uses ports 4000/4001. The UE config (`ue_zmq.conf`) remains on ports 2000/2001. The broker bridges the gap, forwarding and impairing IQ data in both directions. Port 3001 is reserved by the jrtc REST server and must not be used for the broker.

### 2.2 Data Flow (Per Direction)

Each direction (DL and UL) runs in its own thread:

1. Receive a "ready" request from downstream (REP socket)
2. Forward the request to upstream (REQ socket)
3. Receive IQ data from upstream (interleaved float32 I/Q samples)
4. Apply the impairment chain (in order):
   - (a) Estimate original signal power (RMS^2, before fading)
   - (b) If fading is enabled: update the Rician/Rayleigh coefficient, complex-multiply IQ by h
   - (c) Add AWGN noise (power relative to pre-fading signal)
   - (d) If interference is enabled (DL only): inject CW tone or narrowband noise at the configured SIR
5. Send impaired IQ data downstream

---

## 3. Channel Models

### 3.1 AWGN (Always Active)

Additive White Gaussian Noise is applied to each I and Q component independently.

- **Signal power estimation**: per-subframe RMS^2 computed from all float samples
- **Noise standard deviation**: `noise_std = sqrt(sig_power / snr_linear)` where `snr_linear = 10^(snr_db / 10)`
- **RNG**: per-thread `rand_r()` with Box-Muller transform (C broker); `numpy.random` (GRC broker)
- Noise is injected only when signal power exceeds 1e-20 (avoids amplifying silence/zero-padding)

### 3.2 Rician Flat Fading (`--fading`)

A time-varying complex channel gain using a first-order autoregressive (AR1) model based on Jake's/Clarke's Doppler spectrum, extended with a Line-of-Sight (LoS) component:

- **Rician K-factor**: controls the ratio of LoS power to scattered power. K = 0 yields pure Rayleigh (no LoS); K -> infinity approaches AWGN-like behaviour. Specified in dB via `--k-factor` (default: 3 dB).
- **Channel coefficient**: `h = h_LoS + h_scatter` where `h_LoS = sqrt(K/(K+1))` (constant) and `h_scatter = sqrt(1/(K+1)) * (h_I + j * h_Q)` (time-varying Rayleigh component)
- **AR1 update** (scatter): `h_I[n] = alpha * h_I[n-1] + sigma_inn * N(0,1)` (analogous for h_Q)
- **Correlation**: `alpha = J_0(2 * pi * f_d * T)` where J_0 is the zeroth-order Bessel function, f_d is the maximum Doppler frequency, and T is the subframe duration
- **Innovation**: `sigma_inn = sqrt((1 - alpha^2) * 0.5)`, preserving unit mean power for the scatter component
- **Complex multiply**: `y_I = h_I * x_I - h_Q * x_Q`, `y_Q = h_I * x_Q + h_Q * x_I`
- **Deep fades**: with low K-factor, |h|^2 can temporarily approach zero, causing SINR drops, MCS adaptation, and bursty HARQ failures. Higher K limits fade depth (the LoS component prevents complete nulls).

Noise power is computed from **pre-fading** signal power; during deep fades the signal is attenuated while noise remains constant, causing the instantaneous SNR to drop sharply.

**K-factor impact on worst-case fade depth:**

| K (dB) | K (linear) | Max Fade Depth | Behaviour |
|--------|-----------|----------------|----------|
| -100 | ~0 | Unbounded (complete null) | Pure Rayleigh; connection crashes likely |
| 0 | 1 | ~20--30 dB | Severe fading |
| 3 | 2 | ~15--25 dB | Moderate; triggers HARQ failures |
| 6 | 4 | ~10--15 dB | Gentle; retransmissions but rarely failures |
| 10 | 10 | ~5--8 dB | Mild; near-AWGN with slight variation |

### 3.3 3GPP Frequency-Selective Fading (GRC Broker Only)

Multi-tap FIR filters from 3GPP TS 36.104 Table B.2, implemented via `scipy.signal.lfilter` with persistent `zi` state for seamless cross-subframe filtering:

| Profile | Taps | Max Delay | Default Doppler | Use Case |
|---------|------|-----------|-----------------|----------|
| **EPA** | 7 | 410 ns | 5 Hz | Extended Pedestrian A -- gentle ISI |
| **EVA** | 9 | 2,510 ns | 70 Hz | Extended Vehicular A -- moderate ISI |
| **ETU** | 9 | 5,000 ns | 300 Hz | Extended Typical Urban -- heavy ISI |

Each tap has an independent AR(1) Jake's fading process. When DL uses frequency-selective fading, UL is automatically downgraded to Flat Rician (`fading_mode = min(mode, 1)`) to prevent deep fades on PUCCH that would destroy HARQ ACK decoding and trigger RRC timeouts.

### 3.4 Carrier Frequency Offset (GRC Broker Only, `--cfo`)

Cumulative phase rotation `exp(j * 2*pi * cfo * t + phi_0)` stressing UE synchronisation tracking. Range: +/-500 Hz. CFO is applied after fading and before AWGN.

### 3.5 Burst Error Injection (GRC Broker Only, `--drop-prob`)

Random subframe drops (entire subframe zeroed) simulating deep fades or interference blanking. Range: 0--25%. Applied as the first step in the impairment chain.

### 3.6 Time-Varying Scenarios (GRC Broker Only, `--scenario`)

| ID | Name | Cycle | SNR | Doppler | Drop Prob |
|----|------|-------|-----|---------|-----------|
| 1 | Drive-by | 30 s sine | 30 -> 15 -> 30 dB | 5 -> 200 -> 5 Hz | 0 -> 2% -> 0 |
| 2 | Urban Walk | Random walk | 12--35 dB | 1--20 Hz | 0 or 5% (15% chance) |
| 3 | Edge of Cell | 60 s linear | 30 -> 8 dB | 5 Hz (fixed) | 0 -> 10% |

Parameters are updated every 1 second. Selection via `--scenario drive-by|urban-walk|edge-of-cell`.

---

## 4. Interference Simulation

Both brokers support **DL-only interference injection** simulating co-channel or adjacent-channel interferers. Interference is applied as the final impairment step on the DL relay path only; the UL relay thread is never affected.

### 4.1 CW (Continuous-Wave Tone) -- C and GRC Brokers

A single-tone sinusoidal interferer at a configurable offset frequency:

- **Amplitude**: `A = sqrt(P_signal / SIR_linear)` where P_signal is measured per-subframe
- **Phase continuity**: cumulative phase maintained across subframe boundaries
- **Signal model**: `I(n) = A * cos(2*pi * f_int * n/fs + phi)`, `Q(n) = A * sin(2*pi * f_int * n/fs + phi)`

### 4.2 Narrowband (1 PRB Bandlimited Noise) -- GRC Broker Only

Complex AWGN bandlimited to 180 kHz (one 5G NR PRB) at a configurable frequency offset:

- **Generation**: white complex AWGN -> FFT -> zero bins outside `[f_int - 90 kHz, f_int + 90 kHz]` -> IFFT -> normalise to target SIR power
- **Frequency shift**: complex carrier `exp(j * 2*pi * f_int * n/fs + phi)` applied after bandlimiting, with cumulative phase maintained across subframes
- **Auto-routing**: `--interference-type narrowband` in the launch script automatically selects the GRC broker

### 4.3 SIR (Signal-to-Interference Ratio)

`SIR = 10 * log_10(P_signal / P_interferer)` in dB. Lower SIR corresponds to stronger interference. Interference power is always scaled to the current signal power, so the SIR is maintained even as fading varies the signal level.

### 4.4 GUI Controls (GRC Broker)

| Row | Controls |
|-----|----------|
| 3 | SIR slider (-10 to 40 dB), Interference Type combo (None / CW Tone / Narrowband 1 PRB) |
| 4 | Interference Frequency slider (+/-11 MHz) |

### 4.5 Validated Results (CW Interference, Live Pipeline)

| SIR (dB) | MAC DL SINR | FAPI UL SNR | Ping RTT (mean) |
|----------|-------------|-------------|-----------------|
| Inf (none) | 25.4 dB | 25.4 dB | ~5 ms |
| 20 | ~20 dB | ~23 dB | ~7 s |
| 10 | 3.6 dB | 19.3 dB | ~39 s |

Ping RTT degrades sharply because the DL path carries both user data and scheduling/ACK signals. FAPI UL SNR is minimally affected because interference is DL-only.

---

## 5. GRC Python Broker Details

### 5.1 Architecture

```
                    srsran_channel_broker.py
                    +--------------------------------------------+
                    |  channel_broker_source (gr.sync_block)     |
                    |  +-------------+  +-------------+         |
  gNB :4000 ---REQ->|  DL Thread   |  |  UL Thread   |<--REQ-- UE :2001
                    |  | Fading+AWGN |  | Fading+AWGN |         |
  UE  :2000 <--REP--|  | CFO+Drop   |  | (Rician)    |--REP--> gNB :4001
                    |  +------+------+  +-------------+         |
                    |         | viz_buf (DL IQ samples)          |
                    |         v                                  |
                    |  +-------------------------------------+   |
                    |  | GUI: Freq Sink | Time Sink | Const  |   |
                    |  |     Waterfall  | Sliders   | Combos |   |
                    |  +-------------------------------------+   |
                    +--------------------------------------------+
```

The ZMQ relay runs in two daemon threads (DL and UL), independent of the GNU Radio scheduler. The `work()` method copies the latest DL IQ buffer into the GR flowgraph for visualisation only. Slider and combo box changes propagate immediately to the relay threads via thread-safe mutable-list callbacks.

### 5.2 Impairment Chain (Per Subframe, Per Direction)

Applied in order inside `relay_thread()`:

1. **Burst drop** -- if `rng.random() < drop_prob`: zero the entire subframe
2. **Fading** -- flat (Rician/Rayleigh AR1) or frequency-selective (FIR lfilter)
3. **CFO** -- cumulative phase rotation across subframes
4. **AWGN** -- `noise_std = sqrt(sig_power / snr_linear)` (skipped for frequency-selective modes where ISI provides sufficient impairment)
5. **Interference** (DL only) -- CW tone or narrowband noise at the configured SIR

### 5.3 QT GUI Controls

| Row | Controls |
|-----|----------|
| 0 | SNR slider (5--40 dB), K-factor slider (-10 to 20 dB) |
| 1 | Doppler slider (0.1--300 Hz), Fading mode combo (Off / Flat Rician / Flat Rayleigh / EPA / EVA / ETU) |
| 2 | CFO slider (+/-500 Hz), Drop probability slider (0--25%), Scenario combo |
| 3 | SIR slider (-10 to 40 dB), Interference Type combo |
| 4 | Interference Frequency slider (+/-11 MHz) |

Visualisation panels (rows 5 and 7): frequency spectrum (2048-pt FFT, Blackman-Harris), IQ time-domain waveform, constellation diagram, and waterfall spectrogram.

### 5.4 Performance Budget

At 23.04 MHz sample rate, each subframe is 23,040 samples and must be processed within 1 ms:

| Direction | Processing Time | Margin |
|-----------|----------------|--------|
| DL (EPA FIR + CFO + AWGN) | 413 us | 587 us headroom |
| UL (Flat Rician + AWGN) | 503 us | 497 us headroom |

### 5.5 Dependencies

GNU Radio 3.10.1.1 (`gnuradio-runtime`, `gnuradio-qtgui`, `gnuradio-blocks`), PyQt5, scipy, numpy 1.26.4, packaging.

---

## 6. CLI Reference

### 6.1 C Broker (`zmq_channel_broker`)

```bash
# Build
gcc -O2 -o zmq_channel_broker zmq_channel_broker.c -lzmq -lm -lpthread

# AWGN only (default: 28 dB SNR both directions)
./zmq_channel_broker

# AWGN + Rician fading (default K=3 dB, fd=5 Hz)
./zmq_channel_broker --snr 28 --fading

# Gentle Rician (higher K = shallower fades)
./zmq_channel_broker --snr 30 --fading --k-factor 6

# Vehicular fading (70 Hz Doppler)
./zmq_channel_broker --snr 15 --fading --doppler 70

# Pure Rayleigh (no LoS; may crash UE)
./zmq_channel_broker --snr 35 --fading --rayleigh

# Asymmetric DL/UL
./zmq_channel_broker --dl-snr 20 --ul-snr 8 --dl-doppler 10 --ul-doppler 70

# CW interference at 1 MHz offset, SIR=10 dB
./zmq_channel_broker --interference-type cw --interference-freq 1000000 --sir 10

# CW interference combined with Rician fading
./zmq_channel_broker --fading --interference-type cw --interference-freq 500000 --sir 20
```

### 6.2 Launch Script (`launch_mac_telemetry.sh`)

```bash
# C broker with Rician fading (recommended -- triggers HARQ failures)
./launch_mac_telemetry.sh --fading

# GRC broker with EPA fading
./launch_mac_telemetry.sh --grc --profile epa --snr 28

# GRC broker with live QT GUI
./launch_mac_telemetry.sh --gui --fading

# EVA + CFO + burst drops
./launch_mac_telemetry.sh --grc --profile eva --cfo 100 --drop-prob 0.05

# Time-varying scenario
./launch_mac_telemetry.sh --gui --fading --scenario edge-of-cell

# CW interference
./launch_mac_telemetry.sh --interference-type cw --sir 10

# Narrowband interference (auto-selects GRC broker)
./launch_mac_telemetry.sh --interference-type narrowband --sir 15

# Perfect channel (no broker)
./launch_mac_telemetry.sh --no-broker

# Stop
./stop_mac_telemetry.sh
```

**Default configuration variables** (editable in the launch script):

| Variable | Default | Description |
|----------|---------|-------------|
| `ZMQ_BROKER_SNR` | 28 | SNR in dB |
| `ZMQ_BROKER_K_FACTOR` | 3 | Rician K-factor in dB |
| `ZMQ_BROKER_DOPPLER` | 5 | Maximum Doppler frequency in Hz |
| `ZMQ_BROKER_INTF_TYPE` | none | Interference type (none / cw / narrowband) |
| `ZMQ_BROKER_INTF_FREQ` | 1000000 | Interference frequency offset in Hz |
| `ZMQ_BROKER_SIR` | 20 | Signal-to-interference ratio in dB |

### 6.3 SNR Guidelines

| SNR (dB) | Impairment Level | Expected Effect |
|----------|-----------------|-----------------|
| 30+ | Minimal | Near-perfect; slight SINR variation |
| 28 | **Recommended** | **HARQ failures with K=3 fading; stable connection** |
| 25 | Moderate | More failures; risk of connection loss with low K |
| 20 | Heavy | Frequent MCS drops; high retransmissions |
| 15 | Severe | MCS drops to 0; frequent HARQ failures |
| 10 | Extreme | MCS 14 avg UL; 1000+ retransmissions |
| 5 | Destructive | UE may fail to attach |
| < 3 | Unusable | Initial access likely impossible |

### 6.4 Doppler Guidelines

| Doppler (Hz) | Scenario | Fade Behaviour |
|--------------|----------|----------------|
| 5 | Stationary | Very slow fades (seconds between deep nulls) |
| 10 | Pedestrian (~3 km/h) | Slow fades (~100 ms coherence time) |
| 70 | Vehicular (~50 km/h) | Moderate fades (~3.5 ms coherence) |
| 300 | Highway (~200 km/h) | Fast fades; bursty errors |
| 900 | High-speed train | Very fast; may prevent stable connection |

---

## 7. Measured Results

### 7.1 Comparison Across Channel Conditions

| Metric | Perfect | AWGN-only (10 dB) | Rayleigh (10 dB) | Rayleigh (20 dB) | **Rician K=3 (28 dB)** |
|---|---|---|---|---|---|
| SINR mean | 42.5 dB | 12.3 dB | 5.3 dB | -7.8 dB | **~35 dB** |
| SINR range (avg) | 42--43 | 10--15 | -32..+18 | -12..+26 | **-36..+65** |
| CQI range | 15 (constant) | 8--10 | 0--15 | 15 | **15 (constant)** |
| DL MCS mean | 27.5 | 14 | -- | 2.3 | **~27** |
| DL retransmissions | 0 | ~1,000 | 3,803 | 12,535 | **~9,400** |
| DL HARQ failures | 0 | 0 | 375 | 48 | **12 (bursty)** |
| UL retransmissions | 0 | 1,046 | 716 | 1,953 | **low** |
| UL HARQ failures | 0 | 0 | 73 | 474 | **0** |
| UE stability | Stable | Stable | **Lost sync ~2 min** | **Stable 5+ min** | **Stable 15+ min** |

### 7.2 Key Observations

**AWGN-only** produces constant degradation (flat SINR, fixed MCS), which is unrealistic. UL is more impacted than DL due to lower UE TX power (tx_gain = 50 vs gNB tx_gain = 75).

**Rayleigh fading** produces time-varying SINR, full MCS range utilisation, and bursty error patterns correlated with deep fades. However, pure Rayleigh causes connection loss within approximately 2 minutes due to sustained complete nulls.

**Rician fading (K=3, SNR=28)** is the recommended configuration. It produces 12 HARQ failures across 2 deep fade events during a 15+ minute run while maintaining a stable connection. Deep fades reach -53 dB on DL, pushing effective SINR to -36 dB -- sufficient to exhaust all 4 HARQ retransmission attempts -- but the LoS component ensures these nulls are brief enough that the RRC layer does not time out.

### 7.3 HARQ Failure Tuning Results

| Config | K (dB) | SNR (dB) | fd (Hz) | Duration | HARQ Failures | Result |
|--------|--------|----------|---------|----------|---------------|--------|
| K=4, SNR=25 | 4 | 25 | 5 | ~4 min | N/A | Crashed |
| K=4, SNR=28 | 4 | 28 | 5 | ~1 min | N/A | Crashed |
| K=6, SNR=25 | 6 | 25 | 5 | ~1.5 min | N/A | Crashed |
| K=6, SNR=30 | 6 | 30 | 5 | 5+ min | 0 | Stable; no failures |
| K=3, SNR=30 | 3 | 30 | 5 | 7+ min | 0 | Stable; no failures |
| **K=3, SNR=28** | **3** | **28** | **5** | **15+ min** | **12** | **Stable with failures** |

HARQ failures require SINR dips below approximately 15--18 dB (the LDPC decoding threshold). With K=3 and SNR=28, occasional deep fades push effective SINR to -36 dB, but the LoS component ensures these nulls are brief enough that the RRC layer does not trigger a UE context release.

### 7.4 Realism Assessment

The recommended Rician configuration produces qualitatively correct telemetry patterns: time-varying SINR, adaptive MCS, and bursty HARQ failures matching expected MAC scheduler behaviour for a mobile channel with a dominant LoS path.

Remaining limitations:
- **SINR +65 dB peaks**: artifact of ZMQ's perfect IQ pipeline with no RF frontend noise floor (real systems cap around 30--35 dB)
- **Flat fading only (C broker)**: all subcarriers fade together; the GRC broker addresses this with EPA/EVA/ETU profiles
- **No inter-cell interference**: single UE, single cell setup
- **No UL power control**: UL power control loops are not modelled
- **CQI always 15**: CQI is computed inside the UE and is not affected by IQ-level noise injection

---

## 8. Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Broker dies immediately | ZMQ EFSM state machine violation from `EAGAIN` on REQ socket | Each step retries in a tight loop; `EINTR` is also handled |
| Port conflicts | Ports 2000/2001 (UE), 4000/4001 (gNB), 3001 (jrtc REST) are reserved | Run `sudo fuser -k 2000/tcp 2001/tcp 4000/tcp 4001/tcp` to clear stale bindings |
| UE fails to attach | SNR too low for initial access (PRACH/RACH) | Increase SNR to 15--20 dB |
| UE loses sync with fading | Sustained deep fade causes PBCH SFN mismatch | Use Rician fading (`--fading`) instead of Rayleigh; increase base SNR |
| srsUE "Permission denied" on log | Launch script redirects stdout to same file as srsUE `[log] filename` | Launch script redirects to `/tmp/ue_stdout.log` to avoid conflict |
| GRC broker `--gui` fails | X11/Wayland display not available | Use `--grc` for headless operation; ensure `DISPLAY` is set for GUI mode |
| Pipeline dies after ~3 min | iperf3 starts before TUN interface is ready; no traffic triggers bearer inactivity release | Launch script waits up to 15 s for TUN IP before starting iperf3 |

---

## 9. Files

| File | Description |
|------|-------------|
| `scripts/zmq_channel_broker.c` (~560 lines) | C broker: Rician/Rayleigh flat fading + AWGN + CW interference |
| `scripts/zmq_channel_broker` | Compiled C binary |
| `scripts/srsran_channel_broker.py` (~1050 lines) | GRC Python broker: superset of C broker with EPA/EVA/ETU, CFO, drops, scenarios, narrowband interference, GUI |
| `config/gnb_zmq_jbpf.yml` | gNB config (ports 4000/4001 for broker) |
| `config/ue_zmq.conf` | srsUE config (ports 2000/2001, unchanged) |

### Reverting to Perfect Channel

To bypass the broker and run with a direct gNB-UE connection:

1. Use `./launch_mac_telemetry.sh --no-broker`, or
2. Manually change `gnb_zmq_jbpf.yml` to ports 2000/2001 and skip starting the broker.
