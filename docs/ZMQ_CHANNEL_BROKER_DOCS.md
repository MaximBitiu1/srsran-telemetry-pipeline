# ZMQ Channel Broker — RF Impairment Simulation for srsRAN ZMQ Radio

## Overview

This document describes the ZMQ Channel Broker, a custom IQ-level noise injection
and fading tool built to simulate non-ideal RF channel conditions in the srsRAN
5G NR ZMQ-based simulation environment. The broker supports AWGN noise injection
and Rician flat fading (with Rayleigh as a special case). It was written from
scratch for this project — no pre-existing tool exists for this purpose.

### Problem Statement

The srsRAN 5G stack uses ZMQ virtual radio to connect the gNB and srsUE without
physical RF hardware. By default, this creates a **perfect channel** — zero noise,
zero fading, zero delay — which yields unrealistically constant telemetry:

| Metric (Perfect Channel) | Value |
|---|---|
| SINR | 42–43 dB (constant) |
| CQI | 15 (maximum, constant) |
| DL MCS | 27–28 (maximum) |
| UL MCS | 28 (maximum, constant) |
| HARQ retransmissions | 0 |
| HARQ failures | 0 |

To make the MAC scheduler telemetry meaningful — showing MCS adaptation, HARQ
retransmissions, SINR variation, etc. — we needed to introduce realistic channel
impairments.

---

## Options Considered

We evaluated three approaches to add channel impairments:

### Option 1: srsUE Built-in Channel Emulator (ATTEMPTED — FAILED)

srsRAN 4G ships with a channel emulator supporting AWGN, fading models (EPA, EVA,
ETU at various Doppler speeds), and propagation delay. We configured it in
`ue_zmq.conf`:

```ini
[channel.dl]
enable       = true
awgn.enable  = true
awgn.snr     = 18
fading.enable = true
fading.model  = eva70
delay.enable  = true
delay.delay_us = 5

[channel.ul]
enable       = true
awgn.enable  = true
awgn.snr     = 18
fading.enable = true
fading.model  = eva70
delay.enable  = true
delay.delay_us = 5
```

**Result**: After running the full pipeline and collecting telemetry, the data was
**identical** to the perfect channel — SINR 42–43, MCS 27–28, zero retransmissions.
The channel emulator had no effect.

**Root cause (confirmed via source code inspection)**: The channel emulator is
wired into the **LTE PHY path only** (`srsue/src/phy/sync.cc` lines 88–90, which
checks `dl_channel_args.enable`). The NR PHY path (`srsue/src/phy/nr/`) has
**zero references** to the channel emulator code. Since our setup runs NR-only
(`[rat.eutra] nof_carriers = 0`), the `[channel.*]` config sections are parsed
but silently ignored at runtime.

**Verdict**: ❌ Not viable for 5G NR. Would require patching the srsUE NR PHY.

### Option 2: Patch srsRAN NR PHY Source Code

We could modify `srsue/src/phy/nr/` to integrate the existing channel emulator
(the `srsran_channel_t` struct and `srsran_channel_run()` function from the LTE
path) into the NR sample processing pipeline.

**Pros**: Would enable all channel models (AWGN, EPA/EVA/ETU fading, delay) natively.

**Cons**: Requires deep changes to the NR PHY code, understanding the NR sample
path, recompilation of srsRAN 4G, and ongoing maintenance if the codebase updates.
Risk of introducing subtle PHY bugs.

**Verdict**: ⚠️ Viable but high effort, invasive, and fragile.

### Option 3: ZMQ Channel Broker (CHOSEN ✅)

A standalone C program that sits between gNB and UE at the ZMQ transport layer,
intercepting IQ samples and injecting AWGN noise before forwarding.

**Pros**:
- **Zero modifications** to srsRAN source code (gNB or UE)
- Works at IQ level — affects **all** physical layer processing (PRACH, PDSCH,
  PUSCH, PUCCH, CSI-RS, etc.)
- All 5 MAC telemetry codelets show changed behavior (CRC, BSR, UCI, DL HARQ, UL HARQ)
- Simple to build (~260 lines of C), single binary, no dependencies beyond libzmq
- Configurable SNR per direction (DL/UL) via CLI flags
- Can be enabled/disabled via `--no-broker` flag without any config changes
- Runs in a separate process — can be killed/restarted independently

**Cons**:
- No frequency-selective fading (all subcarriers fade equally) or propagation delay
- Adds minimal latency (one extra ZMQ hop per direction)

**Why this option won**: It produces the **maximum observable change** across all
telemetry codelets with the minimum implementation complexity. The noise injection
at IQ level is the most fundamental impairment — it degrades everything downstream
(channel estimation, demodulation, decoding) without needing to understand or
modify the PHY internals of either gNB or UE. The fading model was later evolved
from Rayleigh to Rician to create realistic time-varying channel conditions while
maintaining connection stability.

---

## Architecture

### Port Topology

```
Original (perfect channel):
  gNB TX → :2000 (REP) ← UE RX (REQ)
  UE  TX → :2001 (REP) ← gNB RX (REQ)

With broker (impaired channel):
  gNB TX → :4000 (REP) ← Broker DL (REQ) → [Fading+AWGN] → :2000 (REP) ← UE RX (REQ)
  UE  TX → :2001 (REP) ← Broker UL (REQ) → [Fading+AWGN] → :4001 (REP) ← gNB RX (REQ)
```

The gNB config (`gnb_zmq_jbpf.yml`) is changed from ports 2000/2001 to 4000/4001.
The UE config (`ue_zmq.conf`) remains unchanged (ports 2000/2001). The broker
bridges the gap, forwarding and corrupting IQ data in both directions.

**Port 3001 is reserved** by the jrtc REST server — do not use it for the broker.

### Data Flow (per direction)

Each direction (DL and UL) runs in its own thread:

1. **Receive request** from downstream (REP socket) — the ZMQ radio protocol
   sends an empty "ready" message to request the next subframe of IQ samples
2. **Forward request** to upstream (REQ socket) — pass the "ready" message through
3. **Receive IQ data** from upstream — a buffer of interleaved float32 I/Q samples
4. **Apply channel impairments** (in order):
   - (a) Estimate original signal power (RMS², before fading)
   - (b) If fading enabled: update Rayleigh coefficient, complex-multiply IQ by h
   - (c) Add AWGN noise (power relative to pre-fading signal, so deep fades cause
     real SNR drops)
5. **Send impaired IQ data** downstream — the receiver sees degraded samples

### Channel Models

#### AWGN (Always Active)

- **Additive White Gaussian Noise** — Gaussian random samples added to each I
  and Q component independently
- **Signal power estimation**: Per-subframe RMS² computed from all float samples
- **Noise standard deviation**: `noise_std = sqrt(sig_power / snr_linear)` where
  `snr_linear = 10^(snr_db/10)`
- **RNG**: Per-thread `rand_r()` seeded from `time()` + unique XOR salt, with
  Box-Muller transform for Gaussian pairs
- Noise is only injected when signal power exceeds 1e-20 (avoids amplifying
  silence/zero-padding)

#### Rician Flat Fading (Optional, `--fading`)

Time-varying complex channel gain using a first-order autoregressive (AR1) model
based on Jake's/Clarke's Doppler spectrum, extended with a Line-of-Sight (LoS)
component (Rician fading):

- **Rician K-factor**: Controls the ratio of LoS power to scattered power.
  `K=0` → pure Rayleigh (no LoS), `K→∞` → AWGN-like (dominant LoS).
  Specified in dB via `--k-factor`. Default: 3 dB.
- **Channel coefficient**: `h = h_LoS + h_scatter` where
  `h_LoS = sqrt(K/(K+1))` (constant) and
  `h_scatter = sqrt(1/(K+1)) × (h_I + j·h_Q)` (time-varying Rayleigh)
- **AR1 update** (scatter component): `h_I[n] = α·h_I[n-1] + σ_inn·N(0,1)` (same for h_Q)
- **Correlation**: `α = J₀(2π·f_d·T)` where J₀ is the Bessel function of first
  kind (order 0), f_d is max Doppler frequency, T is subframe duration
- **Innovation**: `σ_inn = √((1 - α²)·0.5)` preserving unit mean power for scatter
- **Complex multiply**: `y_I = h_I·x_I - h_Q·x_Q`, `y_Q = h_I·x_Q + h_Q·x_I`
- **Deep fades**: With low K-factor, |h|² can temporarily drop near 0, causing
  SINR drops, MCS adaptation, and bursty HARQ failures. Higher K-factor limits
  the fade depth (LoS component prevents complete nulls).
- **Key property**: Higher Doppler = faster fade rate; higher K = shallower fades

Noise power is computed from **pre-fading** signal power, so during deep fades
the signal is attenuated but noise stays constant → instantaneous SNR plummets.

**K-factor impact on worst-case fade depth:**

| K (dB) | K (linear) | Max fade depth | Behaviour |
|--------|-----------|----------------|----------|
| -100 | ≈0 | ∞ (complete null) | Pure Rayleigh, crashes likely |
| 0 | 1 | ~20–30 dB | Severe fading |
| 3 | 2 | ~15–25 dB | Moderate — triggers HARQ failures |
| 6 | 4 | ~10–15 dB | Gentle — retransmissions but rarely failures |
| 10 | 10 | ~5–8 dB | Mild — near-AWGN with slight variation |

---

## Files

| File | Description |
|---|---|
| `~/Desktop/zmq_channel_broker.c` | C broker source code (Rician/Rayleigh + AWGN) |
| `~/Desktop/zmq_channel_broker` | Compiled C binary |
| `~/Desktop/srsran_channel_broker.py` | GRC Python broker (extends C broker with EPA/EVA/ETU, CFO, drops, scenarios, GUI) |
| `~/Desktop/launch_mac_telemetry.sh` | Pipeline launcher (defaults: K=3, SNR=28, fd=5) |
| `~/Desktop/stop_mac_telemetry.sh` | Pipeline teardown (includes broker stop) |
| `~/Desktop/telemetry_to_influxdb.py` | Python ingestor (decoder JSON → InfluxDB) |
| `~/Desktop/plot_all_telemetry.py` | Comprehensive 15-plot generator (all 17 schemas) |
| `~/Desktop/plots/*.png` | 15 generated telemetry plots |
| `~/Desktop/grafana/` | Grafana installation + dashboard provisioning |
| `~/Desktop/grafana/dashboards/srsran-5g-nr-telemetry.json` | 39-panel Grafana dashboard |
| `~/Desktop/srsRAN_Project_jbpf/configs/gnb_zmq_jbpf.yml` | gNB config (ports 4000/4001) |
| `~/Desktop/ue_zmq.conf` | srsUE config (ports 2000/2001, unchanged) |
| `/tmp/zmq_broker.log` | Broker runtime log |

---

## Building

```bash
gcc -O2 -o zmq_channel_broker zmq_channel_broker.c -lzmq -lm -lpthread
```

**Dependencies**: `libzmq3-dev` (ZeroMQ), standard math and pthreads.

---

## Usage

### Standalone

```bash
# AWGN only (default: 28 dB SNR on both DL and UL)
./zmq_channel_broker

# Custom SNR (both directions)
./zmq_channel_broker --snr 15

# AWGN + Rician fading (default K=3 dB, fd=5 Hz)
./zmq_channel_broker --snr 28 --fading

# Gentle Rician fading (higher K = shallower fades)
./zmq_channel_broker --snr 30 --fading --k-factor 6

# AWGN + vehicular fading (70 Hz Doppler)
./zmq_channel_broker --snr 15 --fading --doppler 70

# Pure Rayleigh fading (no LoS, deep nulls, may crash UE)
./zmq_channel_broker --snr 35 --fading --rayleigh

# Fading only (negligible AWGN)
./zmq_channel_broker --fading --doppler 70 --snr 100

# Asymmetric: different DL/UL SNR and Doppler
./zmq_channel_broker --dl-snr 20 --ul-snr 8 --dl-doppler 10 --ul-doppler 70

# Help
./zmq_channel_broker --help
```

### Via Launch Script

```bash
# AWGN only (default, SNR=28 dB)
./launch_mac_telemetry.sh

# AWGN + Rician fading (recommended — triggers HARQ failures)
./launch_mac_telemetry.sh --fading

# Gentle fading (no HARQ failures, stable telemetry)
./launch_mac_telemetry.sh --fading --k-factor 6 --snr 30

# Custom SNR
./launch_mac_telemetry.sh --fading --snr 25

# Without broker (perfect channel)
./launch_mac_telemetry.sh --no-broker

# Tune parameters: edit these in launch_mac_telemetry.sh:
#   ZMQ_BROKER_SNR=28        (dB, default)
#   ZMQ_BROKER_K_FACTOR=3    (dB, default)
#   ZMQ_BROKER_DOPPLER=5     (Hz, default)
```

### SNR Guidelines

| SNR (dB) | Impairment Level | Expected Effect |
|---|---|---|
| 30+ | Minimal | Near-perfect, slight SINR variation |
| 28 | **Recommended** | **HARQ failures with K=3 fading, stable connection** |
| 25 | Moderate | More failures, risk of connection loss with low K |
| 20 | Heavy | Frequent MCS drops, high retx (add `--fading` for realistic variation) |
| 15 | Severe | MCS drops to 0, frequent HARQ failures |
| 10 | Extreme | MCS 14 avg UL, 1000+ retx, HARQ failures |
| 5 | Destructive | UE may fail to attach or drop frequently |
| < 3 | Unusable | Initial access likely impossible |

### Doppler Guidelines

| Doppler (Hz) | Scenario | Fade Behaviour |
|---|---|---|
| 5 | Stationary | Very slow fades (seconds between deep nulls) |
| 10 | Pedestrian (~3 km/h) | Slow fades (~100 ms coherence time) |
| 70 | Vehicular (~50 km/h) | Moderate fades (~3.5 ms coherence) |
| 300 | Highway (~200 km/h) | Fast fades, bursty errors |
| 900 | High-speed train | Very fast, may prevent stable connection |

---

## Measured Results

### Comparison Across All Channel Conditions

| Metric | Perfect | AWGN-only (10 dB) | Rayleigh (10 dB) | Rayleigh (20 dB) | **Rician K=3 (28 dB)** |
|---|---|---|---|---|---|
| SINR mean | 42.5 dB | 12.3 dB | 5.3 dB | -7.8 dB | **~35 dB** |
| SINR avg range | 42–43 | 10–15 | -32..+18 | -12..+26 | **-36..+65** |
| SINR abs min/max | 42/43 | 10/15 | -50/+65 | -39/+65 | **-36/+65** |
| CQI range | 15 (constant) | 8–10 | 0–15 | 15 | **15 (constant)** |
| DL MCS mean | 27.5 | 14 | — | 2.3 | **~27** |
| DL MCS range | 27–28 | 10–18 | 0–28 | 0–28 | **0–28** |
| DL retransmissions | 0 | ~1,000 | 3,803 | 12,535 | **~9,400 (retx ratio ~1.01)** |
| DL HARQ failures | 0 | 0 | 375 | 48 | **12 (bursty)** |
| UL retransmissions | 0 | 1,046 | 716 | 1,953 | **low** |
| UL HARQ failures | 0 | 0 | 73 | 474 | **0** |
| UE stability | Stable | Stable | **Lost sync ~2 min** | **Stable 5+ min** | **Stable 15+ min** |

### Key Observations

#### AWGN-only (constant degradation)

1. **UL is far more impacted than DL** — The UE transmits at lower power (tx_gain=50)
   compared to gNB (tx_gain=75), so the same SNR produces worse decoding on UL.
2. **MCS adaptation is working** — The gNB's MAC scheduler correctly adapts MCS
   from 28 (maximum) down to 0 (most robust) based on HARQ feedback.
3. **HARQ retransmission mechanism activates** — 1,046 UL retransmissions shows
   the error correction system is actively recovering from noise-induced errors.
4. **Constant degradation** — SINR stays flat at ~12.3 dB, MCS stays around 14.
   This is unrealistic — real channels have time-varying conditions.

#### Rayleigh Fading + AWGN (time-varying, realistic)

1. **Time-varying SINR** — SINR swings from -12 to +26 dB per reporting window
   (vs flat values with AWGN-only). Deep fades hit -39 dB instantaneously. This
   is the defining characteristic of a fading channel.
2. **Full MCS range utilised** — The MAC scheduler uses MCS 0–28, adapting in
   real-time as channel quality varies. This exercises the full link adaptation
   logic in the scheduler.
3. **Bursty error patterns** — HARQ failures cluster during deep fades rather
   than occurring at a constant rate. This is qualitatively correct for Rayleigh
   fading where errors are correlated in time.
4. **Asymmetric UL/DL impact** — UL suffers more (26.1% retx rate, 8.6% failure
   rate) because the UE has lower TX power margin. A real deployment would use
   power control loops to compensate.
5. **SNR sensitivity** — At SNR=10 + fading, the UE lost synchronisation after
   ~2 minutes (PBCH SFN mismatch during sustained deep fade). At SNR=20 + fading,
   the UE was stable for 5+ minutes with rich telemetry variation.
6. **CQI at SNR=20** — CQI stays at 15 because the wideband average at a 20 dB
   base SNR is still perceived as "excellent" by the UE. Frequency-selective
   fading (not implemented) would produce more CQI variation.

#### Rician Fading + AWGN (K=3, SNR=28 — recommended configuration)

The Rician model was introduced to replace pure Rayleigh fading, which caused
too-frequent connection crashes. By adding a LoS component (K-factor), fade
depths are bounded while still triggering realistic HARQ behaviour.

1. **HARQ failures triggered** — 12 total HARQ failures across 2 deep fade
   events during a 15+ minute run. This is the key result: the connection stays
   alive while producing observable failures in the telemetry.
2. **Deep fades reach -53 dB on DL** — With K=3 dB, the LoS component limits
   but does not eliminate deep fades. Effective SINR momentarily drops to -36 dB
   during the worst fades, enough to exhaust all 4 HARQ retransmission attempts.
3. **Bursty failure pattern** — Failure event 1: 4 failures at min_sinr=-6 dB,
   tx_success_rate=87.6%. Event 2: 8 failures at min_sinr=-36 dB,
   tx_success_rate=76.1%. Failures cluster during deep fades, matching real-world behaviour.
4. **Connection remains stable** — Unlike Rayleigh (K=0) or low-K configurations,
   K=3 prevents the sustained complete nulls that trigger gNB's RRC timeout
   ("RRC container not ACKed within 120msec" → UE context release).
5. **max_retx=4** — All HARQ retries are exhausted during deep fades, then the
   MAC scheduler declares a failure. This exercises the full HARQ state machine.

#### HARQ Failure Tuning — Systematic Test Results

Finding the right K-factor + SNR combination required systematic testing. The
challenge: fading parameters aggressive enough to cause HARQ failures, but not
so aggressive that the RRC layer loses the UE.

| Config | K (dB) | SNR (dB) | fd (Hz) | Duration | HARQ Failures | DL Fade Depth | Result |
|---|---|---|---|---|---|---|---|
| K=4, SNR=25 | 4 | 25 | 5 | ~4 min | N/A | -54.5 dB | **Crashed** (DL faded to -54.5 dB) |
| K=4, SNR=28 | 4 | 28 | 5 | ~1 min | N/A | N/A | **Crashed** (too fast) |
| K=6, SNR=25 | 6 | 25 | 5 | ~1.5 min | N/A | N/A | **Crashed** |
| K=6, SNR=30 | 6 | 30 | 5 | 5+ min | 0 | -40 dB | **Stable** but no failures (SINR floor ~26 dB) |
| K=3, SNR=30 | 3 | 30 | 5 | 7+ min | 0 | -45.6 dB | **Stable** but no failures (retx ratio ~1.007) |
| **K=3, SNR=28** | **3** | **28** | **5** | **15+ min** | **12** | **-53.4 dB** | **Winner — stable + failures** |

**Key insight**: HARQ failures require SINR dips below ~15–18 dB (the turbo/LDPC
decoding threshold). With K=3 + SNR=28, occasional deep fades push effective SINR
to -36 dB — well below the threshold — but the LoS component ensures these nulls
are brief enough that the RRC layer doesn't timeout. Higher SNR (30+) provides
too much headroom for the same K-factor; lower K (≤2 or Rayleigh) causes
too-deep/too-long fades that crash the connection.

#### Realism Assessment

The Rician fading run (K=3, SNR=28) produces **qualitatively correct** telemetry
patterns — time-varying SINR, adaptive MCS, bursty HARQ failures — matching what
a MAC scheduler engineer would expect from a mobile channel. The LoS component
makes this more realistic than pure Rayleigh for urban/suburban deployments where
a dominant path typically exists.

Remaining limitations:
- **SINR +65 dB peaks**: Artifact of ZMQ's perfect IQ pipeline with no RF
  frontend noise floor. Real systems cap around 30–35 dB.
- **Flat fading only**: All subcarriers fade together. Real channels are
  frequency-selective (different subcarriers fade independently).
- **No inter-cell interference**: Single UE, single cell setup.
- **No power control**: UL power control is not modelled.

---

## Troubleshooting

### Broker dies immediately after starting

**Cause**: The original broker code had a bug where `EAGAIN` from a `zmq_recv()`
on the REQ socket caused it to `continue` back to step 1, violating the ZMQ
REQ-REP state machine (EFSM error → thread exit).

**Fix**: Each step now retries in a tight loop until it succeeds or `running`
goes to 0. `EINTR` is also handled (signals from child processes).

### Port conflicts

- Port **3001** is used by the jrtc REST server — never assign it to the broker
- Ports **2000/2001** are used by the UE — the broker binds on these
- Ports **4000/4001** are used by the gNB (via broker) — the broker connects here

If ports are stuck from a previous run:
```bash
sudo fuser -k 2000/tcp 2001/tcp 4000/tcp 4001/tcp
```

### UE fails to attach

At very low SNR (< 5 dB), the UE may fail initial access (PRACH/RACH). Increase
SNR to 15–20 dB and retry.

### UE loses sync with fading enabled

**Symptom**: UE log shows `PBCH-MIB: NR SFN (X) does not match current SFN (Y)`
and telemetry data stops flowing.

**Cause**: A sustained deep fade (Rayleigh |h|² → 0) combined with AWGN causes
the UE to lose PBCH synchronisation. This is more likely at lower SNR where
there is less headroom to survive deep fades.

**Fix**: Increase the base SNR. At SNR=10 + fading, the UE survives ~2 minutes.
At SNR=20 + fading, the UE is stable for 5+ minutes. Use SNR=20 as default
for fading runs.

### srsUE "Permission denied" on log file

This happens when the launch script redirects srsUE stdout to `/tmp/ue.log` while
srsUE also tries to write to the same file via its `[log] filename = /tmp/ue.log`
config. The launch script now redirects to `/tmp/ue_stdout.log` to avoid the
conflict, while srsUE writes structured logs to `/tmp/ue.log`.

---

## Development History

This tool was **written from scratch** — no existing ZMQ noise broker or IQ-level
channel emulator existed for srsRAN's ZMQ radio interface.

### Timeline

1. **Channel emulator attempt** — Configured srsUE's built-in `[channel.dl]` and
   `[channel.ul]` sections with AWGN (SNR=18), EVA-70 fading, and 5µs delay.
   Ran the full pipeline and collected telemetry. Data was identical to perfect
   channel. Investigation revealed the emulator is LTE-only dead code for NR.

2. **Alternatives evaluation** — Assessed three options (see "Options Considered"
   above). Chose the ZMQ broker for maximum telemetry impact with minimum
   complexity.

3. **Initial implementation** — Wrote `zmq_channel_broker.c` (~260 lines): two
   pthreads (DL/UL), ZMQ REQ-REP bridge, Box-Muller AWGN generation, configurable
   SNR via CLI flags. Compiled against libzmq3-dev.

4. **Port conflict resolution** — Initially used ports 3000/3001. Port 3001
   conflicted with the jrtc REST server. Changed to 4000/4001.

5. **ZMQ state machine bug** — The broker crashed after forwarding one message.
   Root cause: `zmq_recv()` with `ZMQ_DONTWAIT` returned `EAGAIN`, and the
   `continue` statement jumped back to step 1 of the 5-step loop. This violated
   the ZMQ REQ-REP protocol (cannot send two requests without receiving a reply),
   producing an `EFSM` error that killed the thread. Fixed by restructuring each
   step into its own retry loop that respects the state machine.

6. **Signal handling hardening** — Added `SIGPIPE` ignore, `SNDTIMEO`/`RCVTIMEO`
   on all sockets, and `EINTR` handling for interrupted system calls caused by
   child process signals.

7. **Process isolation** — Used `setsid` in the launch script to run the broker
   in its own session, preventing signal propagation issues when stopping other
   pipeline components.

8. **Successful AWGN data collection** — At SNR=10 dB, collected 22 seconds of
   telemetry showing dramatic changes across all 5 codelet streams.

9. **Rayleigh flat fading implementation** — Added time-varying complex channel
   gain using a first-order AR1 model based on Jake's/Clarke's Doppler spectrum.
   Uses `J₀(2π·f_d·T)` Bessel correlation coefficient, Box-Muller innovation,
   and complex multiply on IQ pairs. Noise power is computed from pre-fading
   signal power so deep fades cause real SNR drops. Added CLI flags: `--fading`,
   `--doppler`, `--dl-doppler`, `--ul-doppler`, `--srate`.

10. **Fading validation at SNR=10** — First fading test at SNR=10 + fd=10 Hz.
    Collected 381 lines of telemetry showing time-varying SINR (-32 to +18 avg),
    full MCS range, bursty HARQ failures. UE lost PBCH synchronisation after
    ~2 minutes due to sustained deep fade (SFN mismatch errors).

11. **Fading at SNR=20 (stable)** — Increased SNR to 20 dB to provide headroom
    for deep fades. UE stayed connected for 5+ minutes. Collected 1,070+ REC
    messages with rich time-varying telemetry: SINR swinging -12 to +26,
    MCS 0–28, 12,535 DL retransmissions, 474 UL failures. This confirmed the
    fading implementation produces qualitatively realistic channel behaviour.

12. **Multi-codelet expansion** — Expanded from 1 codelet set (MAC, 10 codelets)
    to 11 codelet sets (~60 codelets) covering RLC, PDCP, FAPI, RRC, NGAP, and
    jBPF perf layers. Modified all YAML configs from `DestinationNone` to
    `DestinationUDP`. Updated launch script with `CODELET_SETS` array loop and
    `--snr N` CLI flag. 10/11 sets load successfully (ue_contexts fails — .o not
    compiled). Pipeline produces 17 telemetry schemas, 1,799 messages in 3 min.

13. **SNR=30 default for multi-codelet** — The additional eBPF processing overhead
    from 10 codelet sets (24 hooks) means fading-induced PBCH sync loss occurs
    after ~3 min regardless of SNR. Changed default to 30 dB to maximize headroom.
    UE lifetime under fading is limited by Rayleigh deep fades, not noise floor.

14. **Rayleigh → Rician fading conversion** — Converted the fading model from pure
    Rayleigh to Rician by adding a Line-of-Sight (LoS) component. The Rician model
    splits the channel gain into a constant LoS term `sqrt(K/(K+1))` and a
    time-varying scatter term `sqrt(1/(K+1)) × h_rayleigh`. Added `--k-factor`
    CLI flag (dB). K=0 recovers Rayleigh; K→∞ approaches AWGN. Added `--rayleigh`
    shortcut (`--k-factor -100`). This bounds fade depth: K=6 dB limits worst-case
    fades to ~10–15 dB (vs unlimited for Rayleigh), preventing connection crashes.

15. **Grafana + InfluxDB dashboard** — Built a complete telemetry pipeline: Python
    ingestor (`telemetry_to_influxdb.py`) parses decoder JSON output and writes
    to InfluxDB. Grafana dashboard (39 panels) visualises all 15 InfluxDB
    measurements across MAC, RLC, PDCP, FAPI, RRC, NGAP, and jBPF perf layers.
    Fixed sparse event-driven panels (PDCP DL, RRC Events, NGAP Events) by
    widening their time windows from 5 min to 1–24 hours.

16. **HARQ failure parameter tuning** — Systematically tested 6 fading
    configurations to find one that triggers HARQ failures without crashing:
    K=4/SNR=25 (crashed ~4 min), K=4/SNR=28 (crashed ~1 min), K=6/SNR=25
    (crashed ~1.5 min), K=6/SNR=30 (stable, 0 failures), K=3/SNR=30 (stable,
    0 failures), **K=3/SNR=28 (stable 15+ min, 12 HARQ failures)**. Updated
    script defaults to K=3, SNR=28.

17. **Comprehensive plotting pipeline** — Created `plot_all_telemetry.py` (944
    lines) generating 15 PNG plots covering all 17 telemetry schemas. One plot
    per codelet schema, strictly codelet data only (no synthetic/derived views).
    Handles MAC vs FAPI `crc_stats` disambiguation by `_schema_proto_package`,
    FAPI cumulative÷l1Cnt for true averages, per-bearer aggregation for RLC/PDCP,
    RNTI>1000 UE filtering, and event timelines for RRC/NGAP. Outputs 15 PNGs
    to `~/Desktop/plots/` at 150 DPI via matplotlib Agg backend.

18. **Data validation** — Validated all telemetry data against the channel model
    (SNR=30 + Rayleigh fd=10 Hz). Confirmed: SINR mean=30.3 dB matches config,
    4.6 dB std dev matches Rayleigh statistics, 9.9% deep fades >6 dB below mean,
    HARQ failures correlate with fading dips (23.1 vs 31.2 dB SINR), MCS
    adaptation working (DL 19.7–27.9, UL 18.6–28.0), CQI constant at 15
    (expected — UE-computed). DL-side plots mostly empty because of uplink-only
    iperf3 traffic — verified correct.

19. **Pipeline stability fix (iperf3 TUN race condition)** — Diagnosed pipeline
    crashes that appeared as "GRC instability" but were actually caused by the
    iperf3 client starting before the UE's TUN interface (`tun_srsue`) was ready.
    Without traffic, the gNB triggered `BearerContextInactivityNotification` after
    ~2 minutes of inactivity → clean UE release → pipeline shutdown. The "trap
    invalid opcode" seen in `dmesg` was a harmless CPU ISA issue during process
    exit, not a crash. **Fix**: Modified `launch_mac_telemetry.sh` to wait up to
    15 seconds for `tun_srsue` to obtain an IP before starting the iperf3 client.
    Confirmed: pipeline now runs indefinitely with `--grc --fading --snr 28 --k-factor 3 --doppler 5`.

20. **Supervisor report** — Created `SUPERVISOR_REPORT.md`, a comprehensive
    technical report documenting the full project, GRC broker design rationale,
    GUI visualization, channel parameters, and all telemetry schemas.

21. **GitHub repository setup** — Initialized git repository, added all project
    files, documentation, and configuration, pushed to GitHub for version control.

---

## Reverting to Perfect Channel

To run without the broker (direct gNB↔UE connection):

1. Run `./launch_mac_telemetry.sh --no-broker`, or
2. Manually change `gnb_zmq_jbpf.yml` back to ports 2000/2001:
   ```yaml
   device_args: tx_port=tcp://127.0.0.1:2000,rx_port=tcp://127.0.0.1:2001,base_srate=23.04e6
   ```
   and skip starting the broker.

---

## GNU Radio Python Channel Broker (`srsran_channel_broker.py`)

### Overview

The GNU Radio (GRC) channel broker is a Python replacement for the C broker that
adds **five capabilities the C broker cannot provide**:

1. **Frequency-selective fading** (3GPP EPA / EVA / ETU multi-tap FIR filters)
2. **Carrier Frequency Offset (CFO)** injection
3. **Burst error injection** (random subframe drops)
4. **Time-varying scenarios** (Drive-by, Urban Walk, Edge-of-cell)
5. **Live QT GUI** with interactive sliders and real-time spectrum/constellation visualization

The GRC broker uses the **same ZMQ relay architecture** as the C broker (ports
4000/4001 ↔ 2000/2001), the same adaptive per-subframe AWGN (measuring actual
signal power), and the same AR(1) Jake's Bessel Rician/Rayleigh flat fading. It
is a strict **superset** of the C broker's capabilities.

### File

| File | Lines | Description |
|------|-------|-------------|
| `~/Desktop/srsran_channel_broker.py` | ~950 | GRC broker (Python, GNU Radio 3.10.1.1) |

### Dependencies

- GNU Radio 3.10.1.1 (`gnuradio-runtime`, `gnuradio-qtgui`, `gnuradio-blocks`)
- PyQt5, scipy, numpy 1.26.4, packaging

### Architecture

```
                    srsran_channel_broker.py
                    ┌────────────────────────────────────────────┐
                    │  channel_broker_source (gr.sync_block)     │
                    │  ┌─────────────┐  ┌─────────────┐         │
  gNB :4000 ───REQ──►│  DL Thread   │  │  UL Thread   │◄──REQ── UE :2001
                    │  │ Fading+AWGN │  │ Fading+AWGN │         │
  UE  :2000 ◄──REP──│  │ CFO+Drop   │  │ (Rician)    │──REP──► gNB :4001
                    │  └──────┬──────┘  └─────────────┘         │
                    │         │ viz_buf (DL IQ samples)          │
                    │         ▼                                  │
                    │  ┌─────────────────────────────────────┐   │
                    │  │ GUI: Freq Sink │ Time Sink │ Const  │   │
                    │  │     Waterfall  │ Sliders   │ Combos │   │
                    │  └─────────────────────────────────────┘   │
                    └────────────────────────────────────────────┘
```

**Key design**: The ZMQ relay runs in two daemon threads (DL and UL), independent
of the GNU Radio scheduler. The `work()` method only copies the latest DL IQ
buffer into the GR flowgraph for visualization. Slider/combo box changes propagate
immediately to the relay threads via thread-safe mutable-list callbacks.

### Impairment Chain (per subframe, per direction)

Applied in order inside `relay_thread()`:

1. **Burst drop** — if `rng.random() < drop_prob`: zero the entire subframe
2. **Fading** — flat (Rician/Rayleigh AR1) or frequency-selective (FIR lfilter)
3. **CFO** — cumulative phase rotation `exp(j·2π·cfo·t + φ₀)` across subframes
4. **AWGN** — `noise_std = √(sig_power / snr_linear)` (skipped for freq-selective
   modes where ISI already provides sufficient impairment)

### 3GPP Delay Profiles (TS 36.104 Table B.2)

| Profile | Taps | Max Delay | Default Doppler | Use Case |
|---------|------|-----------|-----------------|----------|
| **EPA** | 7 | 410 ns | 5 Hz | Extended Pedestrian A — gentle ISI |
| **EVA** | 9 | 2,510 ns | 70 Hz | Extended Vehicular A — moderate ISI |
| **ETU** | 9 | 5,000 ns | 300 Hz | Extended Typical Urban — heavy ISI |

Each tap has an independent AR(1) Jake's fading process. The FIR filter is applied
via `scipy.signal.lfilter` with persistent `zi` state for seamless cross-subframe
filtering (no boundary discontinuities).

### UL Fading Strategy

When DL uses frequency-selective fading (EPA/EVA/ETU), UL is automatically
downgraded to **Flat Rician** (`fading_mode = min(mode, 1)`). This prevents deep
fades on PUCCH that would kill HARQ ACK decoding and cause RRC timeouts. The UL
path also skips CFO and burst drops.

### Time-Varying Scenarios

| ID | Name | Cycle | SNR | Doppler | Drop Prob |
|----|------|-------|-----|---------|-----------|
| 1 | Drive-by | 30s sine | 30→15→30 dB | 5→200→5 Hz | 0→2%→0 |
| 2 | Urban Walk | random walk | 12–35 dB | 1–20 Hz | 0 or 5% (15% chance) |
| 3 | Edge of Cell | 60s linear | 30→8 dB | 5 Hz (fixed) | 0→10% |

Scenarios update parameters every 1 second (QTimer in GUI, threading.Event in
headless). Select via `--scenario drive-by|urban-walk|edge-of-cell`.

### QT GUI Controls

The GUI window (launched with `--gui` flag) provides:

| Row | Controls |
|-----|----------|
| 0 | SNR slider (5–40 dB), K-factor slider (-10–20 dB) |
| 1 | Doppler slider (0.1–300 Hz), Fading mode combo (Off / Flat Rician / Flat Rayleigh / EPA / EVA / ETU) |
| 2 | CFO slider (±500 Hz), Drop probability slider (0–25%), Scenario combo |

**Visualization panels** (4):
- Frequency spectrum (2048-pt FFT, Blackman-Harris)
- IQ time-domain waveform (I and Q traces)
- Constellation diagram (I/Q scatter)
- Waterfall (time-frequency spectrogram)

All changes propagate **immediately** to the relay threads.

### Usage

```bash
# GRC broker with flat Rician fading (same as C broker, plus GUI)
./launch_mac_telemetry.sh --gui --fading

# EPA frequency-selective fading
./launch_mac_telemetry.sh --grc --profile epa --snr 28

# EVA + CFO + burst drops (headless)
./launch_mac_telemetry.sh --grc --profile eva --cfo 100 --drop-prob 0.05

# Time-varying scenario with GUI
./launch_mac_telemetry.sh --gui --fading --scenario urban-walk

# Maximum dynamic behaviour (recommended for rich Grafana plots)
./launch_mac_telemetry.sh --gui --fading --snr 20 --k-factor 0 --doppler 10 --cfo 50 --drop-prob 0.03 --scenario urban-walk

# Standalone (without launch script)
python3 srsran_channel_broker.py --snr 28 --fading --profile epa
python3 srsran_channel_broker.py --snr 20 --fading --doppler 10 --cfo 50 --drop-prob 0.03 --scenario urban-walk
python3 srsran_channel_broker.py --snr 28 --fading --no-gui  # headless
```

### AWGN Bug Fix (Critical)

The original AWGN implementation used `noise_std = 1/√(2·SNR_linear)`, assuming
unit signal power. However, srsRAN ZMQ samples have actual power ≈ 0.002, making
the noise 16× too strong (effective SNR ≈ 0.5 dB instead of 28 dB). The UE crashed
instantly. Fixed to measure actual signal power per subframe:
`noise_std = √(sig_power / snr_linear)` — matching the C broker exactly.

### Performance Budget

At 23.04 MHz sample rate, each subframe is 23,040 samples and must be processed
within 1 ms. Measured processing times (EPA fading, SNR=28):

| Direction | Time | Margin |
|-----------|------|--------|
| DL (EPA FIR + CFO + AWGN) | 413 µs | 587 µs headroom |
| UL (Flat Rician + AWGN) | 503 µs | 497 µs headroom |

AWGN is skipped for freq-selective modes (ISI provides sufficient impairment),
which is essential for staying within the real-time budget.

---

## Pipeline Components (Full Architecture)

```
┌─────────────┐     ┌────────────────────┐     ┌─────────────┐
│   jrtc      │     │  ZMQ Channel Broker │     │   srsUE     │
│  (runtime   │     │  (Rician + AWGN)    │     │  (UE sim)   │
│  controller)│     │                     │     │             │
└──────┬──────┘     │  gNB:4000 ←→ :2000  │     │  RX :2000   │
       │            │  UE :2001 ←→ :4001  │     │  TX :2001   │
       │            └─────────┬───────────┘     └──────┬──────┘
       │                      │                        │
┌──────┴──────┐        ┌──────┴──────┐          ┌──────┴──────┐
│  gNB+jbpf   │        │  Reverse    │          │  iperf3     │
│  (5G base   │◄──────►│  Proxy      │          │  (traffic   │
│   station)  │  IPC   │  :30450     │          │   generator)│
│  TX :4000   │        └──────┬──────┘          └─────────────┘
│  RX :4001   │               │
└──────┬──────┘        ┌──────┴──────┐
       │               │  Decoder    │
       │               │  gRPC:20789 │──► /tmp/decoder.log
       │               │  UDP :20788 │
       │               └─────────────┘
       │
       └──► jbpf hooks across entire protocol stack:
            MAC (CRC, BSR, UCI, DL/UL HARQ), FAPI (DL/UL TTI, CRC, RACH),
            RLC (DL/UL SDU/PDU), PDCP (DL/UL PDU/SDU), RRC (UE lifecycle),
            NGAP (procedures), perf (hook timing)
            → ~60 eBPF codelets collect & aggregate stats
            → 17 telemetry schemas sent via jbpf output channels
```

### Startup Order

1. **jrt-controller** — manages jbpf lifecycle
2. **ZMQ Channel Broker** — noise injection (optional, skipped with `--no-broker`)
3. **gNB** — 5G base station with jbpf hooks
4. **Reverse Proxy** — bridges IPC socket to TCP for codelet management
5. **Decoder** — decodes protobuf telemetry to JSON (runs in xterm window)
6. **Load Codelets** — deploys eBPF codelets + registers protobuf schemas (10 codelet sets, ~60 codelets)
7. **srsUE + iperf3** — attaches UE and generates UDP traffic

### Shutdown Order (reverse)

1. iperf3 → 2. srsUE → 3. Decoder → 4. Reverse Proxy → 5. gNB → 6. ZMQ Broker → 7. jrtc

---

## Telemetry Codelets

### MAC Codelets (mac_stats.yaml — 10 codelets)

| # | Codelet | Hook Point | Key Metrics |
|---|---|---|---|
| 1 | `mac_stats_collect` | CRC indication | SINR, RSRP, TX count, success, HARQ failures, retx histogram |
| 2 | `mac_stats_collect` | BSR received | Buffer status: report count, total bytes |
| 3 | `mac_stats_collect` | PHR received | Power headroom reports |
| 4 | `mac_stats_collect` | UCI PDU | CQI, RI, SR detection, time advance offset |
| 5 | `mac_stats_collect_dl_harq` | DL HARQ ACK | MCS, TBS, retransmission stats, per-type breakdown |
| 6 | `mac_stats_collect_ul_harq` | UL HARQ CRC | MCS, TBS, retransmission stats, per-type breakdown |
| 7 | `mac_sched_crc_stats` | Scheduler tick | Flushes CRC aggregates to output |
| 8 | `mac_sched_bsr_stats` | Scheduler tick | Flushes BSR aggregates to output |
| 9 | `mac_sched_uci_pdu_stats` | Scheduler tick | Flushes UCI aggregates to output |
| 10 | `mac_sched_ue_deletion` | UE removal | Cleans up hash maps for disconnected UEs |

All MAC stats are **cumulative** (never reset) — each report contains running totals since codelet load.

### Additional Codelet Sets (Loaded from ~/Desktop/jrtc-apps/codelets/)

| Codelet Set | YAML Config | Codelets | Output Schemas | Layer |
|---|---|---|---|---|
| **rlc** | `rlc_stats.yaml` | 11 | `rlc_dl_stats`, `rlc_ul_stats` | RLC |
| **pdcp** | `pdcp_stats.yaml` | 10 | `dl_stats`, `ul_stats` | PDCP |
| **fapi_dl_conf** | `fapi_gnb_dl_config_stats.yaml` | 2 | `dl_config_stats` | FAPI (PHY-MAC) |
| **fapi_ul_conf** | `fapi_gnb_ul_config_stats.yaml` | 2 | `ul_config_stats` | FAPI (PHY-MAC) |
| **fapi_ul_crc** | `fapi_gnb_crc_stats.yaml` | 2 | `crc_stats` (FAPI) | FAPI (PHY-MAC) |
| **fapi_rach** | `fapi_gnb_rach_stats.yaml` | 2 | `rach_stats` | FAPI (PHY-MAC) |
| **rrc** | `rrc.yaml` | 5 | `rrc_ue_add`, `rrc_ue_procedure`, `rrc_ue_remove`, `rrc_ue_update_context`, `rrc_ue_update_id` | RRC |
| **ngap** | `ngap.yaml` | 3 | `ngap_procedure_started`, `ngap_procedure_completed`, `ngap_reset` | NGAP |
| **ue_contexts** | `ue_contexts.yaml` | 12 | DU/CU-CP/E1AP lifecycle events | UE Context | 
| **perf** | `jbpf_stats.yaml` | 1 | `jbpf_out_perf_list` | jBPF internals |

**Note**: The `ue_contexts` set fails to load because `du_ue_ctx_creation.o` is
not compiled (only `.cpp` source exists). All other 10 sets load successfully.

All non-MAC YAML configs were modified from `forward_destination: DestinationNone`
to `forward_destination: DestinationUDP` to enable telemetry output to the decoder.
Originals are backed up as `.bak.none` files.

### Cross-Layer Telemetry Streams (17 Active Schemas)

The full pipeline produces **17 telemetry schemas** across the entire 5G NR
protocol stack:

| Layer | Schema | Type | Typical Rate |
|---|---|---|---|
| **FAPI** | `dl_config_stats` | Periodic | ~50/min |
| **FAPI** | `ul_config_stats` | Periodic | ~48/min |
| **FAPI** | `crc_stats` (FAPI) | Periodic | ~48/min |
| **FAPI** | `rach_stats` | Event-driven | 1 per attach |
| **MAC** | `crc_stats` (MAC) | Periodic | ~95/min |
| **MAC** | `harq_stats` | Periodic | ~96/min |
| **MAC** | `uci_stats` | Periodic | ~52/min |
| **MAC** | `bsr_stats` | Periodic | ~47/min |
| **RLC** | `rlc_dl_stats` | Periodic | ~51/min |
| **RLC** | `rlc_ul_stats` | Periodic | ~50/min |
| **PDCP** | `dl_stats` | Periodic | ~1/min |
| **PDCP** | `ul_stats` | Periodic | ~50/min |
| **RRC** | `rrc_ue_add` | Event-driven | 1 per attach |
| **RRC** | `rrc_ue_procedure` | Event-driven | ~3 per session |
| **RRC** | `rrc_ue_remove` | Event-driven | 1 per detach |
| **NGAP** | `ngap_procedure_started` | Event-driven | ~3 per session |
| **NGAP** | `ngap_procedure_completed` | Event-driven | ~3 per session |
| **jBPF** | `jbpf_out_perf_list` | Periodic | ~60/min |

### Multi-Codelet Run Results (SNR=28, Rician K=3 dB, fd=5 Hz — Recommended Config)

**Duration**: 15+ minutes, **17 schemas**, 24 jBPF hooks monitored, **HARQ failures triggered**

| Metric | Value |
|---|---|
| RLC DL PDU TX bytes | 1,117 |
| RLC DL AM retransmissions | 1 |
| PDCP DL data PDU TX bytes | 771 |
| FAPI DL MCS range | 0–4122 (aggregated) |
| FAPI UL MCS range | 84–13494 (aggregated) |
| RACH timing advance | 0 (single PRACH, 1 report) |
| RACH power | 20 dBm |
| RRC UE Add events | 1 (cRnti=17921, pci=1) |
| RRC UE Procedures | 3 (all successful) |
| RRC UE Remove events | 1 (UE lost sync to fading) |
| NGAP procedures started | 3 (InitialUEMessage, InitialContextSetup, UEContextRelease) |
| NGAP procedures completed | 3 (all successful) |
| jBPF hooks monitored | 24 (across all codelet sets) |

**Key observations**:
- All protocol layers producing data: FAPI → MAC → RLC → PDCP → RRC → NGAP
- Periodic streams (MAC, RLC, FAPI) fire every ~1s — good for time-series analysis
- Event-driven streams (RRC, NGAP, RACH) fire during UE lifecycle events only
- Cross-layer visibility enables tracing fading impact through the entire stack
- UE survives ~3 min with fading regardless of SNR (deep fades cause PBCH sync loss)
- The `rrc_ue_remove` and `ngap_procedure_completed(UEContextRelease)` events
  confirm the gNB correctly handles UE disconnection caused by fading
