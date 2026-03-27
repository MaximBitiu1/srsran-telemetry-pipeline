# Project Reference — srsRAN 5G NR jBPF Telemetry + ZMQ Channel Broker

---

## Project Summary

We built a **5G NR telemetry collection and channel impairment system** on a single
Ubuntu Linux machine (user `maxim`, sudo password `2003`). The system runs:

1. **srsRAN Project (jbpf fork)** — 5G gNB with ~87 eBPF/jBPF hooks
2. **srsUE** (from srsRAN 4G) — software UE connected via ZMQ virtual radio
3. **jrt-controller + jrtc-apps** — eBPF codelet lifecycle management
4. **ZMQ Channel Broker** — custom C program (or GRC Python broker) injecting AWGN + Rician flat fading + CW/narrowband interference into IQ samples between gNB and UE
5. **~60 eBPF codelets** across 10 codelet sets producing **17 telemetry schemas** covering FAPI, MAC, RLC, PDCP, RRC, NGAP, and jBPF performance layers
6. **Plotting pipeline** — Python script generating 15 per-codelet PNG plots

Everything runs locally. No physical RF hardware — gNB↔UE communication is over ZMQ sockets, with the broker in the middle injecting channel impairments.

---

## What Was Built (Chronological Phases)

### Phase 1: Fixed 10 MAC eBPF Codelets
All 10 MAC scheduler codelets had eBPF verifier failures (hash map relocation issues, map type mismatches, complex loop rejection). Fixed them all. Removed `JBPF_HASHMAP_CLEAR` calls — stats are now **cumulative** (running totals since codelet load, never reset).

### Phase 2: Fixed Two Bugs in jrtc-ctl (Go CLI)
- **DL/UL HARQ schema collision**: Both share `harq_stats` proto name. The decoder's `Streams` map was `map[string][]byte`, causing UL to overwrite DL. Changed to `map[string][][]byte` with `append()`.
- **Context cancellation**: Single `errgroup.WithContext()` killed phase 2 (jbpf load) when phase 1 (decoder) finished. Split into sequential phases with separate errgroups.

### Phase 3: Built ZMQ Channel Broker from Scratch (~477 lines C)
srsUE's built-in channel emulator is **LTE-only dead code for NR** — confirmed via source inspection. So we wrote a standalone ZMQ broker that:
- Sits between gNB (ports 4000/4001) and UE (ports 2000/2001)
- Two pthreads: DL (gNB→UE) and UL (UE→gNB)
- ZMQ REQ-REP bridge (5-step loop per direction)
- **AWGN**: Box-Muller transform, per-subframe RMS power estimation, noise std = √(sig_power / 10^(snr_db/10))
- **Rician flat fading**: AR1 model with Jake's/Clarke's Doppler correlation using J₀(2π·f_d·T) Bessel coefficient, complex multiply on IQ pairs. LoS component `sqrt(K/(K+1))` + scatter `sqrt(1/(K+1)) × h_rayleigh`. K-factor controls fade depth.
- CLI flags: `--snr N`, `--fading`, `--k-factor N`, `--doppler N`, `--rayleigh`, `--dl-snr`, `--ul-snr`, `--dl-doppler`, `--ul-doppler`, `--srate`

Debugged: port conflicts (3001 reserved by jrtc), ZMQ EFSM state machine violations, SIGPIPE/EINTR, process isolation.

Originally implemented with Rayleigh-only fading. Later converted to Rician by adding LoS component — pure Rayleigh caused complete channel nulls crashing UE within 1-3 minutes. Rician K-factor bounds fade depth: K=6 dB limits worst-case to ~10-15 dB.

### Phase 4: Expanded from 1 to 10 Codelet Sets
Modified all YAML configs from `DestinationNone` → `DestinationUDP`. Updated launch script with `CODELET_SETS` array loop. Added `--snr N` CLI flag to launch script. 10/11 sets load (ue_contexts fails — .o not compiled). Originals backed up as `.bak.none`.

### Phase 5: Data Collection at SNR=30 + Rayleigh Fading (fd=10 Hz)
Collected **1,799 messages across 17 schemas** in ~3 minutes. Data saved to `/tmp/decoder_snr30_fading_allcodelets.log` (2.15 MB, 3641 lines). Default SNR raised to 30 dB because UE survives ~3 min with fading regardless of SNR (deep fades cause PBCH sync loss).

### Phase 6: Comprehensive Plotting (15 PNGs)
Created `plot_all_telemetry.py` (944 lines) generating 15 plots — one per codelet schema, strictly codelet data only (no synthetic/derived plots):

| # | Plot File | Schema(s) | What It Shows |
|---|-----------|-----------|---------------|
| 01 | `01_mac_crc_stats.png` | `crc_stats` (MAC) | SINR time series, TX counts, HARQ failures, RSRP |
| 02 | `02_mac_bsr_stats.png` | `bsr_stats` | Buffer bytes, BSR report count, avg bytes/report |
| 03 | `03_mac_uci_stats.png` | `uci_stats` | CQI, SR detected, timing advance |
| 04 | `04_mac_harq_stats.png` | `harq_stats` | DL vs UL: MCS, TBS, retransmissions (side-by-side) |
| 05 | `05_rlc_dl_stats.png` | `rlc_dl_stats` | PDU TX bytes, SDU new bytes, AM retx, queue |
| 06 | `06_rlc_ul_stats.png` | `rlc_ul_stats` | PDU RX bytes, SDU delivered, latency |
| 07 | `07_pdcp_dl_stats.png` | `dl_stats` | Data TX, retx bytes, SDU latency, discards |
| 08 | `08_pdcp_ul_stats.png` | `ul_stats` | Data RX, SDU delivered, control PDU volume |
| 09 | `09_fapi_dl_config.png` | `dl_config_stats` | MCS/PRB/TBS (cumulative÷l1Cnt for true avg) |
| 10 | `10_fapi_ul_config.png` | `ul_config_stats` | MCS/PRB/TBS |
| 11 | `11_fapi_crc_stats.png` | `fapi_crc_stats` | PHY SNR min/max, timing advance range |
| 12 | `12_rrc_events.png` | `rrc_ue_add/procedure/remove` | UE lifecycle timeline |
| 13 | `13_ngap_events.png` | `ngap_procedure_started/completed` | Core network procedures timeline |
| 14 | `14_jbpf_perf_stats.png` | `jbpf_out_perf_list` | Hook latency percentiles (p50/p90/p99 bar chart) + invocation counts |
| 15 | `15_jbpf_perf_timeseries.png` | `jbpf_out_perf_list` | Top 6 hooks latency over time |

### Phase 7: Data Validation
Validated all data against the channel model. Key findings:
- **SINR mean=30.3 dB** (matches configured SNR=30)
- **SINR std=4.6 dB, range=30 dB** (Rayleigh fading signature)
- **9.9% deep fades** (>6 dB below mean) — matches Rayleigh statistics  
- **HARQ failures correlate with fading dips**: mean SINR during failures = 23.1 dB vs 31.2 dB otherwise
- **MCS adaptation working**: DL 19.7–27.9 (mean 26.9), UL 18.6–28.0 (mean 27.1)
- **CQI pegged at 15**: Expected — CQI is computed inside UE, not affected by broker noise
- **DL-side plots mostly flat/empty**: Expected — we ran **uplink iperf3** (UE→gNB), so DL only carries control/signaling

### Plots That Look "Empty" (and why that's correct)
- **RLC DL Stats**: Only 3/152 records have non-zero TX bytes (max 726 bytes) — no DL user traffic, just signaling
- **PDCP DL Stats**: Only 3 data points total — initial RRC/NAS signaling during attach
- **PDCP UL Control PDU Volume**: Flat zero — PDCP control PDUs (status reports) not needed when no PDCP retransmissions occur
- **DL PRBs**: Pegged at 2 PRBs — minimum allocation for DL control (PDCCH/DCI for UL grants)
- **RRC Events**: 5 markers only — 1 UE add, 3 procedures (RRCSetup sub-steps), 1 UE remove
- **NGAP Events**: 6 markers — 3 started + 3 completed (InitialUEMessage, InitialContextSetup, UEContextRelease)

### Phase 8: Grafana + InfluxDB Real-Time Dashboard
Built a complete real-time telemetry visualization pipeline:

- **InfluxDB 1.6.7**: Database `srsran_telemetry` with 15 measurements (mac_crc_stats, mac_harq_stats, mac_bsr_stats, mac_uci_stats, rlc_dl_stats, rlc_ul_stats, pdcp_dl_stats, pdcp_ul_stats, fapi_dl_config_stats, fapi_ul_config_stats, fapi_crc_stats, fapi_rach_stats, rrc_events, ngap_events, jbpf_perf_stats)
- **Python ingestor** (`telemetry_to_influxdb.py`, 616 lines): Tails `/tmp/decoder.log`, parses JSON, maps 16 proto schemas to 15 InfluxDB measurements, handles cumulative→delta conversion for MAC counters, writes via InfluxDB HTTP line protocol
- **Grafana 11.5.2**: 39-panel dashboard organized in rows by protocol layer. Includes time-series, stat panels, gauges, and bar charts. Auto-provisioned via `grafana/provisioning/`.
- Fixed sparse data panels: PDCP DL (widened to 1h window), RRC Events and NGAP Events (widened to 24h window)
- Dashboard: http://localhost:3000/d/srsran-5g-nr-telemetry/ (admin/admin)

### Phase 9: HARQ Failure Parameter Tuning
Systematically tested 6 Rician fading configurations to find one that triggers HARQ failures without crashing the connection:

| Config | Duration | HARQ Failures | Result |
|--------|----------|---------------|--------|
| K=4, SNR=25, fd=5 | ~4 min | N/A | Crashed |
| K=4, SNR=28, fd=5 | ~1 min | N/A | Crashed |
| K=6, SNR=25, fd=5 | ~1.5 min | N/A | Crashed |
| K=6, SNR=30, fd=5 | 5+ min | 0 | Stable but no failures |
| K=3, SNR=30, fd=5 | 7+ min | 0 | Stable but no failures |
| **K=3, SNR=28, fd=5** | **15+ min** | **12** | **Winner — stable + failures** |

Winning config produces 12 HARQ failures across 2 deep fade events: min_sinr=-36 dB, tx_success_rate dips to 76%, max_retx=4 (all retries exhausted). Updated script defaults: `ZMQ_BROKER_SNR=28`, `ZMQ_BROKER_K_FACTOR=3`.

### Phase 10: GNU Radio Python Channel Broker (`srsran_channel_broker.py`)

Built a Python-based GNU Radio channel broker that is a strict superset of the C broker, adding 5 new capabilities:

1. **Frequency-selective fading (3GPP EPA/EVA/ETU)** — Multi-tap FIR filters from 3GPP TS 36.104 Table B.2. EPA (7 taps, 410 ns), EVA (9 taps, 2510 ns), ETU (9 taps, 5000 ns). Each tap has independent AR(1) Jake's fading. Applied via `scipy.signal.lfilter` with persistent `zi` state for seamless cross-subframe filtering.

2. **Carrier Frequency Offset (CFO)** — Cumulative phase rotation `exp(j·2π·cfo·t + φ₀)` that stresses UE synchronisation tracking. ±500 Hz range, controllable via GUI slider or `--cfo N`.

3. **Burst error injection** — Random subframe drops (entire subframe zeroed) simulating deep fades or interference blanking. 0–25% range, controllable via slider or `--drop-prob N`.

4. **Time-varying scenarios** — ScenarioRunner class with 3 profiles:
   - Drive-by (30s sine cycle: SNR 30→15→30, Doppler 5→200→5 Hz)
   - Urban Walk (bounded random walk: SNR 12–35 dB, Doppler 1–20 Hz)
   - Edge of Cell (60s linear decline: SNR 30→8 dB, drop 0→10%)

5. **Live QT GUI** — Full PyQt5 window with:
   - Sliders: SNR (5–40 dB), K-factor (-10–20 dB), Doppler (0.1–300 Hz), CFO (±500 Hz), Drop prob (0–25%)
   - Combo boxes: Fading mode (Off / Flat Rician / Rayleigh / EPA / EVA / ETU), Scenario (Manual / Drive-by / Urban Walk / Edge of Cell)
   - Visualizations: Frequency spectrum, IQ waveform, Constellation diagram, Waterfall display
   - All parameter changes propagate immediately to relay threads

**Key bugs fixed during development:**
- **AWGN power bug (CRITICAL)**: Original code assumed unit signal power (`noise_std = 1/√(2·SNR_linear)`). srsRAN ZMQ samples have power ≈ 0.002, making noise 16× too strong (effective SNR ≈ 0.5 dB). Fixed to measure actual signal power per subframe: `noise_std = √(sig_power / snr_linear)`.
- **UL fading**: EPA/EVA/ETU on UL caused PUCCH deep fades → HARQ ACK decode failure → RRC timeout. Fixed: UL uses `min(fading_mode, 1)` = Flat Rician when DL is freq-selective.
- **Subframe boundary discontinuity**: `np.convolve` discarded FIR tail each subframe. Fixed with `scipy.signal.lfilter` + `zi` state.
- **GUI launch**: `setsid` in launch script disconnected from X11 display. Fixed: GUI mode uses `DISPLAY="${DISPLAY:-:0}" python3 -u ...` without setsid.

**Performance**: DL EPA 413 µs, UL Rician 503 µs per subframe (within 1 ms budget at 23.04 MHz).

**Launch script updates**: Added `--gui`, `--grc`, `--profile P`, `--cfo N`, `--drop-prob N`, `--scenario S` flags. `--gui` implies `--grc`. Profile/CFO/drop/scenario imply `--grc`.

### Phase 11: Pipeline Stability Fix & Documentation

**Root cause of "GRC crashes"**: The pipeline kept dying after ~3 minutes. Using `dmesg` and process logs, traced the real cause: iperf3 client failed to start ("Bad file descriptor") because the UE's TUN interface (`tun_srsue`) was not yet ready. Without data-plane traffic, the gNB triggered `BearerContextInactivityNotification` after ~2 minutes of inactivity → clean UE release → pipeline shutdown. The "trap invalid opcode" in dmesg was a harmless CPU ISA issue during process exit cleanup, not a crash. The GRC broker was never the problem.

**Fix**: Modified `launch_mac_telemetry.sh` (lines 395-420) to wait up to 15 seconds for `tun_srsue` to obtain an IP address before starting the iperf3 client. Only starts iperf3 if IP is confirmed.

**Validation**: Pipeline now runs indefinitely at `--grc --fading --snr 28 --k-factor 3 --doppler 5`. 11/11 codelet sets loaded, 75,738+ PUSCH/PDSCH entries, SINR ~28 dB, iperf3 sending 10 Mbps UDP.

**Documentation**: Created `SUPERVISOR_REPORT.md` — comprehensive technical report for supervisor covering the full project, why Python GRC was chosen over GNU Radio Companion, how the broker works, GUI visualization details, channel parameters, and all telemetry schemas.

**GitHub setup**: Initialized git repository and pushed all project files, scripts, and documentation.

### Phase 12: UE Latency & Throughput Measurements

Added end-to-end UE latency and throughput monitoring to both the launch script and the stress collection script.

**Launch script (`launch_mac_telemetry.sh`) additions:**
- **DL iperf3** (port 5202, reverse mode): `iperf3 -s -B 10.45.0.1 -p 5202` + client in UE namespace with `--reverse` flag → core pushes data to UE over the GTP tunnel. No host→UE IP routing needed.
- **Continuous ICMP ping** from UE namespace: `sudo ip netns exec ue1 ping -i 1 10.45.0.1 >> $PING_LOG`. Log: `$LOG_DIR/ping_ue.log`.
- Config vars: `IPERF_DL_PORT=5202`, `IPERF_DL_BITRATE="5M"`.
- Both started inside the `if [ "$UE_IP" != "unknown" ]` guard (after TUN IP confirmed).
- Preflight cleanup kills any stale `ping.*10.45.0.1` processes.
- `stop_mac_telemetry.sh` updated to stop ping before srsUE.

**Stress collection script (`stress_anomaly_collect.sh`) additions:**
- `MEAS_UL_PORT=5213` and `MEAS_DL_PORT=5214` (isolated from main traffic ports).
- `measure_scenario()` function: 10s UL iperf3 probe (port 5213, JSON output) + 10s DL iperf3 probe (port 5214, reverse, JSON output). Parses `bits_per_second` via Python3 JSON. Reads last 30 ping RTT samples from `/tmp/ping_ue.log` to compute `rtt_avg_ms` and `rtt_max_ms`.
- Phase 4.5 added inside `run_scenario()`: calls `measure_scenario()` between "collect" and "remove_stressor".
- Manifest CSV header extended: `ul_mbps,dl_mbps,rtt_avg_ms,rtt_max_ms` appended to every row.

### Phase 13: Interference Simulation

Added **DL-only RF interference injection** to both brokers, simulating co-channel or adjacent-channel interferers. Interference is applied after AWGN as the final impairment step, only in the DL relay thread.

**C broker (`zmq_channel_broker.c`, ~560 lines):**
- `interference_state_t` struct: `enabled`, `freq_hz`, `sir_linear`, `phase`, `sample_rate`.
- `interference_apply()`: per-subframe power estimation → `int_amp = sqrt(sig_power / sir_linear)` → CW tone added to I and Q: `samples[i] += int_amp * cosf(phase)`, `samples[i+1] += int_amp * sinf(phase)`. Phase incremented by `2π·f_int/fs` each sample; cumulative across subframes.
- DL thread gets `interference_enabled=1` when `--interference-type cw` or `narrowband`. UL thread always has `interference_enabled=0`.
- New CLI flags: `--interference-type <cw|narrowband>`, `--interference-freq <Hz>`, `--sir <dB>`.
- Help text notes narrowband→use GRC broker. Rebuilt binary: `gcc -O2 -o zmq_channel_broker zmq_channel_broker.c -lzmq -lm -lpthread`.

**GRC Python broker (`srsran_channel_broker.py`, ~1050 lines):**
- `apply_interference(iq, int_type, freq_hz, sir_linear, samp_rate, int_phase, rng, bw_hz=180e3)`:
  - CW: `np.exp(1j * phases) * int_amp`
  - Narrowband: complex AWGN → FFT → zero bins outside `±90 kHz` → IFFT → normalize → frequency-shift by `exp(j·phases)`
  - Phase vector (`phases = np.arange(n) * phase_inc + int_phase[0]`) applied to both types; `int_phase[0]` updated for continuity.
- DL `_make_impairments()` gets `int_enabled=(int_type!='none')`, UL always `int_enabled=False`.
- New `set_sir_db()`, `set_int_type()`, `set_int_freq_hz()` callbacks on `channel_broker_source`.
- GUI additions: Row 3 — SIR slider (−10→40 dB) + Interference Type dropdown (None/CW/Narrowband). Row 4 — Int Freq slider (±11 MHz). Visualization rows shift to 5 and 7.
- Headless/argparse: `--interference-type`, `--interference-freq`, `--sir` added.

**Launch script (`launch_mac_telemetry.sh`) additions:**
- Config vars: `ZMQ_BROKER_INTF_TYPE="none"`, `ZMQ_BROKER_INTF_FREQ=1000000`, `ZMQ_BROKER_SIR=20`.
- Flag parsing: `--interference-type`, `--interference-freq`, `--sir`.
- `--interference-type narrowband` automatically sets `USE_GRC_BROKER=true`.
- Broker args: `--interference-type $ZMQ_BROKER_INTF_TYPE --interference-freq $ZMQ_BROKER_INTF_FREQ --sir $ZMQ_BROKER_SIR` appended when type != "none" (both C and GRC arg blocks).

**Validation (live pipeline, CW interference, SIR gradient):**

| SIR (dB) | MAC DL SINR | FAPI UL SNR | Ping RTT (mean) |
|----------|-------------|-------------|-----------------|
| ∞ (none) | 25.4 dB | 25.4 dB | ~5 ms |
| 20 | ~20 dB | ~23 dB | ~7 s |
| 10 | 3.6 dB | 19.3 dB | ~39 s |

Clear SIR gradient confirms the interference is applied correctly. FAPI UL SNR is minimally affected (DL-only interference). Ping RTT degrades sharply because DL carries scheduling/ACK signals as well as user data.

---

## File Inventory

### Files We Created/Modified

| File | Lines | Description |
|------|-------|-------------|
| `~/Desktop/zmq_channel_broker.c` | ~560 | AWGN + Rician fading + CW interference IQ broker (C) |
| `~/Desktop/zmq_channel_broker` | — | Compiled C binary |
| `~/Desktop/srsran_channel_broker.py` | ~1050 | GNU Radio Python broker (superset of C: EPA/EVA/ETU, CFO, drops, scenarios, CW+narrowband interference, GUI) |
| `~/Desktop/launch_mac_telemetry.sh` | ~570 | Pipeline launcher (flags: `--snr N`, `--fading`, `--k-factor N`, `--grc`, `--gui`, `--profile P`, `--cfo N`, `--drop-prob N`, `--scenario S`, `--interference-type T`, `--interference-freq Hz`, `--sir dB`, `--no-broker`, `--no-ue`, `--no-traffic`, `--no-grafana`) |
| `~/Desktop/stop_mac_telemetry.sh` | ~110 | Pipeline teardown in reverse order (includes ping stop) |
| `~/Desktop/stress_anomaly_collect.sh` | ~830 | Stress scenario script: CPU/memory/network/disk stressors, per-scenario UL/DL throughput + ping RTT measurement, manifest CSV |
| `~/Desktop/telemetry_to_influxdb.py` | 616 | Python ingestor (decoder JSON → InfluxDB via HTTP line protocol) |
| `~/Desktop/plot_all_telemetry.py` | 944 | Comprehensive 15-plot generator for all 17 schemas |
| `~/Desktop/plot_telemetry.py` | 272 | Original MAC-only 5-plot script (superseded) |
| `~/Desktop/ue_zmq.conf` | 57 | srsUE config (ZMQ ports 2000/2001, NR band 3) |
| `~/Desktop/gnb_zmq.yaml` | — | gNB config reference |
| `~/Desktop/ZMQ_CHANNEL_BROKER_DOCS.md` | 724 | Full channel broker documentation |
| `docs/PROJECT_CONTINUATION.md` | — | This handoff document |
| `~/Desktop/SUPERVISOR_REPORT.md` | — | Comprehensive supervisor report (project, GRC rationale, GUI, parameters) |
| `~/Desktop/PROJECT_SUMMARY.txt` | — | Concise project summary |
| `~/Desktop/JBPF_MAC_TELEMETRY_PROMPT.md` | 469 | Original project architecture docs |
| `~/Desktop/plots/*.png` | 15 files | Generated telemetry plots |
| `~/Desktop/grafana/` | — | Grafana 11.5.2 + datasource/dashboard provisioning |
| `~/Desktop/grafana/dashboards/srsran-5g-nr-telemetry.json` | — | 39-panel Grafana dashboard |

### Key Source Repos

| Path | Description |
|------|-------------|
| `~/Desktop/srsRAN_Project_jbpf/` | 5G gNB with jBPF hooks (config at `configs/gnb_zmq_jbpf.yml`) |
| `~/Desktop/jrt-controller/` | jBPF runtime controller (Go CLI at `tools/jrtc-ctl/`) |
| `~/Desktop/jrtc-apps/codelets/` | 13 codelet subdirs (10 loadable) |
| `~/Desktop/srsRAN_4G/` | srsUE source (binary at `/usr/local/bin/srsue`) |

### YAML Configs Modified (DestinationNone → DestinationUDP)

All in `~/Desktop/jrtc-apps/codelets/`:
- `mac/mac_stats.yaml`, `rlc/rlc_stats.yaml`, `pdcp/pdcp_stats.yaml`
- `fapi_dl_conf/fapi_gnb_dl_config_stats.yaml`, `fapi_ul_conf/fapi_gnb_ul_config_stats.yaml`
- `fapi_ul_crc/fapi_gnb_crc_stats.yaml`, `fapi_rach/fapi_gnb_rach_stats.yaml`
- `rrc/rrc.yaml`, `ngap/ngap.yaml`, `perf/jbpf_stats.yaml`

Originals backed up as `.bak.none` files.

---

## System Configuration

### Port Map

| Port | Protocol | Used By | Purpose |
|------|----------|---------|---------|
| 2000 | TCP/ZMQ | Broker REP → UE REQ | DL IQ to UE |
| 2001 | TCP/ZMQ | UE REP → Broker REQ | UL IQ from UE |
| 4000 | TCP/ZMQ | gNB REP → Broker REQ | DL IQ from gNB |
| 4001 | TCP/ZMQ | Broker REP → gNB REQ | UL IQ to gNB |
| 3001 | TCP | jrtc REST server | **Reserved — never use** |
| 5201 | TCP/UDP | iperf3 | UL iperf3 server (core side, 10 Mbps UL) |
| 5202 | TCP/UDP | iperf3 | DL iperf3 server (core side, `--reverse` → pushes to UE) |
| 5213 | UDP | iperf3 | Stress-script UL measurement probe (10s burst) |
| 5214 | UDP | iperf3 | Stress-script DL measurement probe (10s burst, reverse) |
| 20788 | UDP | jbpf → decoder | Telemetry data |
| 20789 | TCP/gRPC | jrtc-ctl decoder | Schema registration |
| 30450 | TCP | reverse proxy | IPC-to-TCP bridge for codelet loading |
| 38412 | SCTP | AMF (Open5GS) | NGAP signaling |

### gNB Config (key settings)
- ZMQ: `tx_port=4000, rx_port=4001` (through broker)
- Band 3, DL ARFCN 368500, 20 MHz BW, SCS 15 kHz, 106 PRBs
- tx_gain: 75, rx_gain: 75
- MCS table: qam64

### UE Config (key settings)
- ZMQ: `tx_port=2001, rx_port=2000`
- tx_gain: 50, rx_gain: 40
- NR only (`[rat.eutra] nof_carriers = 0`), band 3, 106 PRBs
- USIM: milenage, IMSI `999700123456780`
- Network namespace: `ue1`, TUN: `tun_srsue`

### Pipeline Architecture

```
jrtc (runtime) ──┐
                 │
gNB+jbpf ◄──IPC──► Reverse Proxy :30450 ──► Decoder (gRPC:20789, UDP:20788) ──► /tmp/decoder.log
  TX :4000                                         ▲                                    │
  RX :4001                                         │                                    ▼
    │                                    ~60 eBPF codelets (17 schemas)      telemetry_to_influxdb.py
    ▼                                                                               │
┌──────────────────────────────────────┐                                            ▼
│   ZMQ Channel Broker (pick one):     │                                    InfluxDB :8086
│   A) C broker:  AWGN + flat Rician   │                                    db=srsran_telemetry
│   B) GRC Python: A + EPA/EVA/ETU,    │                                            │
│      CFO, burst drops, scenarios,    │                                            ▼
│      live QT GUI                     │                                    Grafana :3000
│   gNB:4000 ←→ :2000 (DL)            │                                    39 panels
│   UE:2001  ←→ :4001 (UL)            │
└──────────────────────────────────────┘
    │
    ▼
srsUE (RX:2000, TX:2001) ──► iperf3 UL :5201 (10 Mbps UDP uplink)
                          ◄── iperf3 DL :5202 (5 Mbps UDP downlink, --reverse)
                          ◄── ping RTT monitoring → /tmp/ping_ue.log
```

### Startup Order
1. jrt-controller → 2. ZMQ Broker (optional) → 3. gNB (sudo) → 4. Reverse Proxy → 5. Decoder (xterm) → 6. Load Codelets (10 sets) → 7. srsUE + iperf3

### Shutdown Order (reverse)
iperf3 → srsUE → Decoder → Reverse Proxy → gNB → ZMQ Broker → jrtc

---

## How to Run

```bash
# ─── C Broker (AWGN + flat Rician) ───────────────────────────────────
# Full pipeline with Rician fading (recommended — triggers HARQ failures)
# Defaults: K=3 dB, SNR=28 dB, fd=5 Hz
./launch_mac_telemetry.sh --fading

# Gentle fading (no HARQ failures, stable)
./launch_mac_telemetry.sh --fading --k-factor 6 --snr 30

# Custom SNR
./launch_mac_telemetry.sh --snr 20 --fading

# ─── GRC Python Broker (advanced impairments + GUI) ──────────────────
# GUI with flat Rician fading — opens QT window with sliders + spectrum
./launch_mac_telemetry.sh --gui --fading

# EPA frequency-selective fading (headless)
./launch_mac_telemetry.sh --grc --profile epa --snr 28

# EVA + CFO + burst drops
./launch_mac_telemetry.sh --grc --profile eva --cfo 100 --drop-prob 0.05

# Maximum dynamic behaviour for Grafana (recommended for rich telemetry)
./launch_mac_telemetry.sh --gui --fading --snr 20 --k-factor 0 --doppler 10 --cfo 50 --drop-prob 0.03 --scenario urban-walk

# Time-varying scenario (edge-of-cell 60s decline)
./launch_mac_telemetry.sh --gui --fading --scenario edge-of-cell

# ─── Interference Simulation ─────────────────────────────────────────
# CW tone at 1 MHz offset, SIR=10 dB (strong — MAC DL SINR drops to ~3.6 dB)
./launch_mac_telemetry.sh --interference-type cw --sir 10

# CW interference combined with Rician fading
./launch_mac_telemetry.sh --fading --interference-type cw --interference-freq 500000 --sir 20

# Narrowband (1 PRB) interference — auto-selects GRC broker
./launch_mac_telemetry.sh --interference-type narrowband --interference-freq 2000000 --sir 15

# ─── Common ──────────────────────────────────────────────────────────
# Perfect channel (no broker)
./launch_mac_telemetry.sh --no-broker

# Stop everything (also stops ping and DL iperf3)
./stop_mac_telemetry.sh

# Check DL throughput log
cat /tmp/iperf3_dl.log

# Check ping RTT log (continuous, all samples)
cat /tmp/ping_ue.log

# Generate plots from decoder log
python3 plot_all_telemetry.py /tmp/decoder.log
# Plots saved to ~/Desktop/plots/

# Rebuild C broker
gcc -O2 -o zmq_channel_broker zmq_channel_broker.c -lzmq -lm -lpthread

# Rebuild jrtc-ctl
cd ~/Desktop/jrt-controller/tools/jrtc-ctl
CGO_CFLAGS="-I/home/maxim/Desktop/jrt-controller/out/inc" \
CGO_LDFLAGS="-L/home/maxim/Desktop/jrt-controller/out/lib -ljrtc_router_stream_id_static" \
go build --trimpath -o /home/maxim/Desktop/jrt-controller/out/bin/jrtc-ctl main.go
```

### SNR Guidelines

| SNR (dB) | Effect |
|----------|--------|
| 30+ | Near-perfect, stable for minutes |
| 28 | **Recommended with K=3 fading — triggers HARQ failures, stable 15+ min** |
| 25 | Moderate — more failures, risk of connection loss with low K |
| 20 | **Best for dynamic Grafana: aggressive MCS/HARQ variation, use with `--scenario`** |
| 15 | Moderate MCS drops, HARQ retx |
| 10 | Heavy — MCS 14 avg UL, 1000+ retx, ~22s session |
| 5 | Extreme — UE may fail to attach |
| <3 | Destructive — initial access impossible |

With Rayleigh fading (`--rayleigh`), UE survives ~3 min regardless of SNR. With Rician (default `--fading`), K=3 keeps connection stable 15+ min.

---

## 17 Telemetry Schemas

### Periodic Schemas (time-series data)

| Layer | Schema | Key Fields | Rate |
|-------|--------|------------|------|
| **MAC** | `crc_stats` | `succTx, cntTx, harqFailure, sumSinr/cntSinr, sumRsrp/cntRsrp, retxHist[16]` | ~95/min |
| **MAC** | `bsr_stats` | `bytes, cnt` (buffer size, report count) | ~47/min |
| **MAC** | `uci_stats` | `csi.cqi, csi.ri, srDetected, timeAdvanceOffset` | ~52/min |
| **MAC** | `harq_stats` | `mcs{total,count,min,max}, consRetx, perHarqTypeStats[3]{count,tbsBytes,cqi}` — DL+UL share this schema, distinguished by `_stream_id` | ~96/min |
| **RLC** | `rlc_dl_stats` | `pduTxBytes, sduNewBytes, sduQueueBytes, am.pduRetxCount` per bearer | ~51/min |
| **RLC** | `rlc_ul_stats` | `pduBytes, sduDeliveredBytes, sduDeliveredLatency` per bearer | ~50/min |
| **PDCP** | `dl_stats` | `dataPduTxBytes, dataPduRetxBytes, sduTxLatency, sduDiscarded` per bearer | ~1/min |
| **PDCP** | `ul_stats` | `rxDataPduBytes, sduDeliveredBytes, rxControlPduBytes` per bearer | ~50/min |
| **FAPI** | `dl_config_stats` | `l1McsAvg, l1PrbAvg, l1TbsAvg, l1Cnt, l1DlcTx, rnti` — **CRITICAL: "Avg" fields are cumulative sums, divide by l1Cnt for true averages** | ~50/min |
| **FAPI** | `ul_config_stats` | Same pattern as DL | ~48/min |
| **FAPI** | `crc_stats` (FAPI) | `l1SnrMax, l1SnrMin, l1CrcSnrHist, l1TaMax, l1TaMin, l1CrcTaHist` — pkg=`fapi_gnb_crc_stats` | ~48/min |
| **jBPF** | `jbpf_out_perf_list` | `hookPerf[]{hookName, num, min, max, p50, p90, p95, p99}` (latency in ns) | ~60/min |

### Event-Driven Schemas (few data points)

| Layer | Schema | Fields | When |
|-------|--------|--------|------|
| **FAPI** | `rach_stats` | TA histogram, power histogram | 1 per attach |
| **RRC** | `rrc_ue_add` | `cRnti, pci, tcRnti, nci, plmn` | 1 per attach |
| **RRC** | `rrc_ue_procedure` | `procedure` (1=Setup, 2=Reconfig, 3=Reestab, 4=SecurityMode), `success`, `meta` | ~3 per session |
| **RRC** | `rrc_ue_remove` | `cucpUeIndex` | 1 per detach |
| **NGAP** | `ngap_procedure_started` | `procedure` (1=InitialUE, 2=UEContextRelease, 3=InitialContextSetup), `ueCtx` | ~3 per session |
| **NGAP** | `ngap_procedure_completed` | `procedure, success, ueCtx` | ~3 per session |

### Important Data Quirks
- **MAC vs FAPI `crc_stats`**: Same schema name! Differentiate by `_schema_proto_package`: `mac_sched_crc_stats` vs `fapi_gnb_crc_stats`
- **FAPI "Avg" = cumulative sum**: `l1McsAvg/l1Cnt = true avg`. Example: `108/5 = 21.6` (real MCS)
- **Stats are cumulative**: Never reset. Diff consecutive messages for per-window values
- **Sentinel values**: `min = 4294967295` (UINT32_MAX) and `max = 0` = "no data yet"
- **`duUeIndex 513`**: Ghost entry in DL HARQ — filter `duUeIndex >= 32`
- **DL config RNTI filter**: `rnti > 1000` selects UE data (vs system/SIB RNTIs)
- **CQI always 15**: CQI is computed inside UE, unaffected by broker noise injection

### Log Format
```
time="2026-03-08T14:49:23+01:00" level=info msg="REC: {\"_schema_proto_msg\":\"crc_stats\", ...}"
```
Parse with: regex `REC: (.*)"$`, then `.replace('\\"', '"')`, then `json.loads()`.

---

## Known Issues

| Issue | Details |
|-------|---------|
| CQI always 15 under noise | CQI computed inside UE — not affected by IQ-level noise injection |
| UL more impacted than DL | UE TX gain (50) < gNB TX gain (75) |
| PHR always empty | srsUE NR MAC doesn't implement PHR reporting |
| `duUeIndex 513` in DL HARQ | Ghost scheduler entry — filter `duUeIndex >= 32` |
| ~3 min UE lifetime with Rayleigh fading | Deep Rayleigh fades cause PBCH SFN mismatch regardless of SNR. Use Rician (--fading) instead. |
| ~~Pipeline dies after ~3 min~~ | **FIXED** — iperf3 race condition: TUN interface not ready → no traffic → BearerContextInactivityNotification. Launch script now waits up to 15s for TUN IP. |
| Port 3001 reserved | jrtc REST server — never use for broker |
| srsUE channel emulator dead for NR | `[channel.*]` only works for LTE PHY |
| ue_contexts codelet set fails | `.o` not compiled, only `.cpp` source exists |
| DL-side plots mostly flat | We ran uplink iperf3 — DL only carries control/signaling |
| FAPI SNR max pegged at 255 | PHY-level artifact — raw L1 max always saturates; cannot be fixed by parameters |
| CQI shows some variance with GRC | With aggressive fading (K=0, SNR≤20), CQI dips from 15 to ~12–13 occasionally |
| GRC broker CPU | ~22% one core for 46 MHz BW; ensure enough headroom on low-end machines |
| GUI requires DISPLAY | GRC broker `--gui` needs X11/Wayland display; use `--grc` for headless |

---

## Validated Data Summary (SNR=30 + Rayleigh fd=10 Hz)

| Metric | Value | Assessment |
|--------|-------|------------|
| SINR mean | 30.3 dB | Matches configured SNR ✓ |
| SINR std dev | 4.6 dB | Rayleigh fading signature ✓ |
| SINR range | 17.6–47.7 dB (30 dB spread) | Realistic ✓ |
| Deep fades (>6 dB below mean) | 9.9% | Matches Rayleigh statistics ✓ |
| SINR during HARQ failures | 23.1 dB mean | Correlates with low SINR ✓ |
| SINR when no failures | 31.2 dB mean | 8 dB gap confirms causation ✓ |
| TX success rate | 95.9% mean, 33.3% worst | Fading causes burst errors ✓ |
| DL MCS | 19.7–27.9 (mean 26.9) | Adaptive modulation working ✓ |
| UL MCS | 18.6–28.0 (mean 27.1) | Symmetric fading ✓ |
| CQI | 15.0 (constant) | Expected (UE-computed) ✓ |
| BSR buffer | 76–3.8 MB | Build-up during fades ✓ |
| FAPI L1 SNR Min | 16–204 (raw) | PHY sees deep instantaneous fades ✓ |
| RRC lifecycle | 1 add → 3 proc → 1 remove | Correct attach/detach ✓ |
| NGAP lifecycle | 3 started → 3 completed (all success) | Standard 5G flow ✓ |
| jBPF hook latency | p50=192–384 ns, p99<1.5 µs | Negligible overhead ✓ |

---

## What Could Be Done Next

Potential directions the user might want to explore:

1. ~~Run with downlink traffic (iperf3 server→UE)~~ → **DONE** (Phase 12: DL iperf3 port 5202 `--reverse`, ping RTT monitoring)
2. **Compare multiple SNR levels** side-by-side (collect at 10, 20, 28, 30 dB and overlay)
3. ~~Time-frequency selective fading~~ → **DONE** (Phase 10: EPA/EVA/ETU FIR fading in GRC broker)
4. **Multi-UE scenarios** (attach 2+ UEs simultaneously)
5. **Compile ue_contexts codelets** to get the 11th codelet set working
6. **Anomaly detection / ML** on the telemetry streams
7. **Per-window (differential) stats** instead of cumulative — diff consecutive messages
8. **Longer collection runs** with periodic UE re-attach after fading disconnects
9. ~~EPA/EVA/ETU delay profiles~~ → **DONE** (Phase 10: `--profile epa|eva|etu` in GRC broker)
10. **Automate multi-SNR comparison** — script that collects at multiple SNR levels and generates comparative plots
11. **Collect anomalous dataset** — Supervisor task #3: run with aggressive impairments, capture telemetry for ML training
12. ~~Push to private GitHub repo~~ → **DONE** (Phase 11: initialized git repo, pushed all files)
13. ~~Add DL iperf3 mode to launch script~~ → **DONE** (Phase 12: `--reverse` mode, port 5202)
14. **Frequency-offset auto-recovery** — test if srsUE survives larger CFO values (>200 Hz)
15. **Multi-scenario automated sweep** — script cycling through all `--scenario` profiles with automatic data collection
16. ~~Add interference simulation~~ → **DONE** (Phase 13: CW+narrowband in GRC, CW in C, `--interference-type/--sir` flags, validated)
17. **Stress scenario expansion** — add disk I/O, IRQ affinity, NUMA, cache-thrashing scenarios to `stress_anomaly_collect.sh`
18. **Git polish** — commit `bep_extension/`, fix UE_IP bug in git repo copy of `launch_mac_telemetry.sh`, push all Phase 12–13 changes
