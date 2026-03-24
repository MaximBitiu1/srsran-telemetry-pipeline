# Pipeline Command Reference

## Start / Stop

```bash
# Start with default config (GRC broker + GUI, Rician fading, SNR=28, K=3, fd=5 Hz)
bash ~/Desktop/launch_mac_telemetry.sh --fading

# Start headless (no GUI window)
bash ~/Desktop/launch_mac_telemetry.sh --fading --grc

# Start with C broker instead of GRC (lighter, no freq-selective fading)
bash ~/Desktop/launch_mac_telemetry.sh --fading --no-grc

# Stop everything
bash ~/Desktop/stop_mac_telemetry.sh
```

## Channel Presets (pass to launch_mac_telemetry.sh)

```bash
# Stable baseline — no impairments
bash ~/Desktop/launch_mac_telemetry.sh

# Winning config — triggers ~12 HARQ failures, stable 15+ min (default with --fading)
bash ~/Desktop/launch_mac_telemetry.sh --fading --snr 28 --k-factor 3 --doppler 5

# Mild stress — EPA 7-tap freq-selective, 2% drops
bash ~/Desktop/launch_mac_telemetry.sh --grc --fading --snr 20 --doppler 10 --profile epa --drop-prob 0.02

# Moderate stress — EVA 9-tap, visible BLER, UE stays up
bash ~/Desktop/launch_mac_telemetry.sh --grc --fading --snr 15 --k-factor 1 --doppler 70 --profile eva --drop-prob 0.05

# Heavy stress (risky — may degrade) — ETU 9-tap, high Doppler, CFO
bash ~/Desktop/launch_mac_telemetry.sh --grc --snr 10 --doppler 200 --profile etu --cfo 100 --drop-prob 0.10

# Rayleigh fading — UE dies in ~3 min, use only for crash testing
bash ~/Desktop/launch_mac_telemetry.sh --rayleigh
```

## Partial Launch Flags

```bash
# Skip UE and traffic (gNB only)
bash ~/Desktop/launch_mac_telemetry.sh --fading --no-ue --no-traffic

# Skip Grafana/InfluxDB stack
bash ~/Desktop/launch_mac_telemetry.sh --fading --no-grafana

# No broker (direct gNB↔UE, no channel impairments)
bash ~/Desktop/launch_mac_telemetry.sh --no-broker
```

## Data Collection

```bash
# Collect 24-scenario anomalous dataset (180s per scenario)
bash ~/Desktop/collect_anomalous_data.sh --duration 180

# Shorter collection for quick test (60s per scenario)
bash ~/Desktop/collect_anomalous_data.sh --duration 60
```

## Telemetry Ingestor

```bash
# Live mode — tail decoder log into InfluxDB (reads from beginning to catch NGAP/RRC events)
python3 ~/Desktop/telemetry_to_influxdb.py --from-beginning

# Replay a saved log file into InfluxDB
python3 ~/Desktop/telemetry_to_influxdb.py --replay /tmp/decoder_snr20_epa.log

# Use a different InfluxDB database
python3 ~/Desktop/telemetry_to_influxdb.py --from-beginning --db my_db
```

## Plotting

```bash
# Generate all 15 telemetry plots from live log
python3 ~/Desktop/plot_all_telemetry.py /tmp/decoder.log

# Generate plots from a saved log
python3 ~/Desktop/plot_all_telemetry.py /tmp/decoder_snr20_epa.log

# Quick single-schema plot
python3 ~/Desktop/plot_telemetry.py /tmp/decoder.log
```

## Broker Validation & Parameter Sweep

```bash
# Validate broker impairment chain (no pipeline needed, 136 tests)
python3 ~/Desktop/validate_broker.py

# Live parameter sweep — runs each preset against the real pipeline
python3 ~/Desktop/sweep_broker_params.py

# List available sweep presets without running
python3 ~/Desktop/sweep_broker_params.py --list

# Run a single named preset
python3 ~/Desktop/sweep_broker_params.py --preset stable
python3 ~/Desktop/sweep_broker_params.py --preset mild
python3 ~/Desktop/sweep_broker_params.py --preset moderate
```

## Grafana & InfluxDB

```bash
# Open dashboard
xdg-open http://localhost:3000/d/srsran-5g-nr-telemetry/

# Query InfluxDB directly
curl "http://localhost:8086/query?db=srsran_telemetry&q=SHOW+MEASUREMENTS"
curl "http://localhost:8086/query?db=srsran_telemetry&q=SELECT+count(succ_tx)+FROM+mac_crc_stats+WHERE+time+>+now()-1h"

# Restart InfluxDB if it gets into a bad state
sudo systemctl restart influxdb
```

## Build / Rebuild

```bash
# Rebuild C channel broker
gcc -O2 -o ~/Desktop/zmq_channel_broker ~/Desktop/zmq_channel_broker.c -lzmq -lm -lpthread

# Rebuild jrtc-ctl
cd ~/Desktop/jrt-controller/tools/jrtc-ctl && \
  CGO_CFLAGS="-I/home/maxim/Desktop/jrt-controller/out/inc" \
  CGO_LDFLAGS="-L/home/maxim/Desktop/jrt-controller/out/lib -ljrtc_router_stream_id_static" \
  go build --trimpath -o /home/maxim/Desktop/jrt-controller/out/bin/jrtc-ctl main.go
```

## Log Files

| File | Contents |
|------|----------|
| `/tmp/decoder.log` | Raw jBPF telemetry (JSON records) |
| `/tmp/gnb.log` | srsRAN gNB output |
| `/tmp/ue.log` | srsUE output |
| `/tmp/broker.log` | Channel broker output |
| `/tmp/ingestor.log` | telemetry_to_influxdb.py output |
| `/tmp/grafana.log` | Grafana server output |
| `/tmp/jrtc.log` | jrtc controller output |
