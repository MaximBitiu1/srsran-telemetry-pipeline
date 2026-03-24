# GRC Channel Broker — Parameter Presets & Safety Guide

## Safe Parameter Ranges

| Parameter    | Safe          | Avoid                                      |
|--------------|---------------|--------------------------------------------|
| SNR          | 20–40 dB      | Below 10 dB → UE drops                    |
| K-factor     | 3–20 dB       | Below 0 dB → deep fades; -10 dB ≈ Rayleigh|
| Doppler      | 1–70 Hz       | Above 200 Hz with Rayleigh → sync loss     |
| Fading mode  | Rician / AWGN | Rayleigh → ~3 min UE lifetime              |
| Fading profile | EPA, EVA    | ETU risky at high Doppler                  |
| CFO          | 0–100 Hz      | 500 Hz may kill initial attach             |
| Drop prob    | 0–5%          | Above 20% → RLC exhaustion → UE drops      |

---

## Recommended Presets

### Stable — no crash
```
--snr 28 --k-factor 3 --doppler 5 --grc --fading
```
SNR=28 dB, K=3 dB, Rician, fd=5 Hz, CFO=0, drop=0

### Winning config (triggers HARQ failures, stable 15+ min)
```
--snr 28 --k-factor 3 --doppler 5 --grc --fading
```
SNR=28 dB, K=3 dB, Rician, fd=5 Hz — produces ~12 HARQ failures without crashing

### Mild stress
```
--snr 20 --k-factor 3 --doppler 10 --grc --profile epa --drop-prob 0.02
```
SNR=20 dB, EPA 7-tap, fd=10 Hz, drop=2% — good for thesis data collection

### Moderate stress
```
--snr 15 --k-factor 1 --doppler 70 --grc --profile eva --drop-prob 0.05
```
SNR=15 dB, EVA 9-tap, fd=70 Hz, drop=5% — visible BLER, UE stays up

### Heavy (risky — may degrade)
```
--snr 10 --doppler 200 --grc --profile etu --cfo 100 --drop-prob 0.10
```
SNR=10 dB, ETU 9-tap, fd=200 Hz, CFO=100 Hz, drop=10%

---

## What Will Crash the Pipeline

- **Rayleigh fading** (mode 2, or K < 0 dB) — UE dies within ~3 min, always
- **SNR below 10 dB** — UE cannot decode; T310 timer expires, RRC drops
- **Drop probability above 20%** — RLC exhausts retransmissions
- **ETU + Doppler > 200 Hz** — combined ISI + fast variation overwhelms equalizer

---

## Quick Reference — Launch Commands

```bash
# Stable baseline
bash ~/Desktop/launch_mac_telemetry.sh --snr 28 --k-factor 3 --doppler 5 --grc --fading

# Mild stress (EPA)
bash ~/Desktop/launch_mac_telemetry.sh --snr 20 --doppler 10 --grc --profile epa

# Moderate stress (EVA)
bash ~/Desktop/launch_mac_telemetry.sh --snr 15 --doppler 70 --grc --profile eva --drop-prob 0.05

# Heavy stress (ETU)
bash ~/Desktop/launch_mac_telemetry.sh --snr 10 --doppler 200 --grc --profile etu --cfo 100 --drop-prob 0.10

# Stop everything
bash ~/Desktop/stop_mac_telemetry.sh
```
