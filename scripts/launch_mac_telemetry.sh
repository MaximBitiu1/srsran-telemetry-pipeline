#!/usr/bin/env bash
# =============================================================================
#  srsRAN jbpf MAC Telemetry — One-Shot Launcher
#  Starts: jrtc → [zmq broker] → gNB → reverse proxy → decoder → codelets → srsUE → iperf3
#
#  Usage:
#    ./launch_mac_telemetry.sh              # full pipeline with C noise broker
#    ./launch_mac_telemetry.sh --fading     # AWGN + Rician fading (K=3 dB)
#    ./launch_mac_telemetry.sh --grc --profile epa   # EPA freq-selective fading
#    ./launch_mac_telemetry.sh --gui --fading         # GRC broker with live QT GUI
#    ./launch_mac_telemetry.sh --grc --cfo 100 --drop-prob 0.05  # CFO + burst drops
#    ./launch_mac_telemetry.sh --grc --scenario drive-by         # time-varying scenario
#    ./launch_mac_telemetry.sh --no-broker  # perfect channel (no noise)
#    ./launch_mac_telemetry.sh --no-ue      # everything except UE + traffic
#
#  Stop everything:
#    ./stop_mac_telemetry.sh
# =============================================================================
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
SUDO_PASS="2003"
SRSRAN_DIR="$HOME/Desktop/srsRAN_Project_jbpf"
JRTC_DIR="$HOME/Desktop/jrt-controller"
JRTC_APPS_DIR="$HOME/Desktop/jrtc-apps"
UE_CONF="$HOME/Desktop/ue_zmq.conf"

GNB_BIN="$SRSRAN_DIR/build/apps/gnb/gnb"
GNB_CFG="$SRSRAN_DIR/configs/gnb_zmq_jbpf.yml"
REVERSE_PROXY_BIN="$SRSRAN_DIR/out/bin/srsran_reverse_proxy"
JRTC_BIN="$JRTC_DIR/out/bin/jrtc"
JRTC_CTL_BIN="$JRTC_DIR/out/bin/jrtc-ctl"
SRSUE_BIN="/usr/local/bin/srsue"
ZMQ_BROKER_BIN="$HOME/Desktop/zmq_channel_broker"
GRC_BROKER_SCRIPT="$HOME/Desktop/srsran_channel_broker.py"
USE_GRC_BROKER=true          # Use GNU Radio channel broker instead of C broker
ZMQ_BROKER_SNR=28            # dB — tuned for HARQ failures without crashing (30=safe, 25=risky)
ZMQ_BROKER_FADING=false      # Rician fading (--fading to enable)
ZMQ_BROKER_DOPPLER=5         # Hz — max Doppler freq (5=slow, 10=pedestrian, 70=vehicular)
ZMQ_BROKER_K_FACTOR=3        # dB — Rician K-factor (6=gentle, 3=HARQ failures, 0=severe, -100=Rayleigh)
ZMQ_BROKER_PROFILE="flat"    # Power delay profile: flat, epa, eva, etu (GRC only)
ZMQ_BROKER_CFO=0             # Hz — carrier frequency offset (GRC only)
ZMQ_BROKER_DROP=0            # Burst drop probability 0-1 (GRC only)
ZMQ_BROKER_SCENARIO="none"   # Time-varying scenario: none, drive-by, urban-walk, edge-of-cell
ZMQ_BROKER_INTF_TYPE="none"  # Interference type: none, cw, narrowband
ZMQ_BROKER_INTF_FREQ=1000000 # Interference centre frequency offset from DC (Hz)
ZMQ_BROKER_SIR=20            # Signal-to-Interference Ratio (dB)
USE_GUI=true                 # Show QT GUI (--gui, only with --grc)

# Grafana + InfluxDB telemetry dashboard
GRAFANA_DIR="$HOME/Desktop/grafana"
GRAFANA_BIN="$GRAFANA_DIR/bin/grafana"
GRAFANA_INI="$GRAFANA_DIR/grafana.ini"
INGESTOR_SCRIPT="$HOME/Desktop/telemetry_to_influxdb.py"
INFLUXDB_HOST="localhost"
INFLUXDB_PORT=8086
INFLUXDB_DB="srsran_telemetry"
START_GRAFANA=true

IPC_SOCKET="/tmp/jbpf/jbpf_lcm_ipc"
REVERSE_PROXY_PORT=30450
DECODER_GRPC_PORT=20789
DECODER_DATA_PORT=20788

# iperf3 traffic settings
IPERF_TARGET="10.45.0.1"
IPERF_PORT=5201
IPERF_BITRATE="10M"          # target UDP bitrate (will exceed ZMQ capacity → drops)
IPERF_DURATION=3600           # seconds of traffic (1 hour)
IPERF_PKT_LEN=1400            # UDP payload size
IPERF_DL_PORT=5202            # DL iperf3 (reverse mode: core → UE)
IPERF_DL_BITRATE="5M"        # DL target bitrate

# Log files
LOG_DIR="/tmp"
LOG_JRTC="$LOG_DIR/jrtc.log"
LOG_GNB="$LOG_DIR/gnb_stderr.log"
LOG_PROXY="$LOG_DIR/reverse_proxy.log"
LOG_DECODER="$LOG_DIR/decoder.log"
LOG_UE="$LOG_DIR/ue.log"
PING_LOG="$LOG_DIR/ping_ue.log"  # continuous ICMP RTT log

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[  OK]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# ── Parse flags ──────────────────────────────────────────────────────────────
START_UE=true
START_TRAFFIC=true
START_BROKER=true
START_WATCHDOG=true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-ue)        START_UE=false; START_TRAFFIC=false ;;
    --no-traffic)   START_TRAFFIC=false ;;
    --no-broker)    START_BROKER=false ;;
    --no-grafana)   START_GRAFANA=false ;;
    --no-watchdog)  START_WATCHDOG=false ;;
    --grc)        USE_GRC_BROKER=true ;;
    --gui)        USE_GUI=true; USE_GRC_BROKER=true ;;
    --fading)     ZMQ_BROKER_FADING=true ;;
    --rayleigh)   ZMQ_BROKER_FADING=true; ZMQ_BROKER_K_FACTOR=-100 ;;
    --k-factor)   ZMQ_BROKER_K_FACTOR="$2"; shift ;;
    --k-factor=*) ZMQ_BROKER_K_FACTOR="${1#*=}" ;;
    --doppler)    ZMQ_BROKER_DOPPLER="$2"; ZMQ_BROKER_FADING=true; shift ;;
    --doppler=*)  ZMQ_BROKER_DOPPLER="${1#*=}"; ZMQ_BROKER_FADING=true ;;
    --snr)        ZMQ_BROKER_SNR="$2"; shift ;;
    --snr=*)      ZMQ_BROKER_SNR="${1#*=}" ;;
    --profile)    ZMQ_BROKER_PROFILE="$2"; USE_GRC_BROKER=true; shift ;;
    --profile=*)  ZMQ_BROKER_PROFILE="${1#*=}"; USE_GRC_BROKER=true ;;
    --cfo)        ZMQ_BROKER_CFO="$2"; USE_GRC_BROKER=true; shift ;;
    --cfo=*)      ZMQ_BROKER_CFO="${1#*=}"; USE_GRC_BROKER=true ;;
    --drop-prob)  ZMQ_BROKER_DROP="$2"; USE_GRC_BROKER=true; shift ;;
    --drop-prob=*) ZMQ_BROKER_DROP="${1#*=}"; USE_GRC_BROKER=true ;;
    --scenario)   ZMQ_BROKER_SCENARIO="$2"; USE_GRC_BROKER=true; shift ;;
    --scenario=*) ZMQ_BROKER_SCENARIO="${1#*=}"; USE_GRC_BROKER=true ;;
    --interference-type) ZMQ_BROKER_INTF_TYPE="$2"; [ "$2" = "narrowband" ] && USE_GRC_BROKER=true; shift ;;
    --interference-type=*) ZMQ_BROKER_INTF_TYPE="${1#*=}"; [ "${1#*=}" = "narrowband" ] && USE_GRC_BROKER=true ;;
    --interference-freq) ZMQ_BROKER_INTF_FREQ="$2"; shift ;;
    --interference-freq=*) ZMQ_BROKER_INTF_FREQ="${1#*=}" ;;
    --sir)        ZMQ_BROKER_SIR="$2"; shift ;;
    --sir=*)      ZMQ_BROKER_SIR="${1#*=}" ;;
    --iperf-bitrate)    IPERF_BITRATE="$2"; shift ;;
    --iperf-bitrate=*)  IPERF_BITRATE="${1#*=}" ;;
    --iperf-dl-bitrate)   IPERF_DL_BITRATE="$2"; shift ;;
    --iperf-dl-bitrate=*) IPERF_DL_BITRATE="${1#*=}" ;;
    -h|--help)
      echo "Usage: $0 [--no-ue] [--no-traffic] [--no-broker] [--grc] [--gui] [--fading] [--snr N] [--k-factor N] [--doppler N] [--rayleigh] [--profile P] [--cfo N] [--drop-prob N] [--scenario S]"
      echo "  --no-ue       Skip starting srsUE and traffic generation"
      echo "  --no-traffic  Start srsUE but skip iperf3 traffic"
      echo "  --no-broker   Skip ZMQ noise broker (perfect channel)"
      echo "  --grc         Use GNU Radio channel broker (enables advanced impairments)"
      echo "  --gui         Show QT GUI with live controls (implies --grc)"
      echo "  --fading      Enable Rician fading (K=${ZMQ_BROKER_K_FACTOR} dB, fd=${ZMQ_BROKER_DOPPLER} Hz)"
      echo "  --rayleigh    Pure Rayleigh fading (deep nulls, may crash UE)"
      echo "  --k-factor N  Rician K-factor in dB (default: 3, higher=gentler)"
      echo "  --doppler N   Max Doppler freq in Hz (default: 5, implies --fading)"
      echo "  --snr N       Set SNR in dB (default: 28)"
      echo "  --profile P   Delay profile: flat, epa, eva, etu (implies --grc)"
      echo "  --cfo N       Carrier freq offset in Hz (implies --grc)"
      echo "  --drop-prob N Burst drop probability 0-1 (implies --grc)"
      echo "  --scenario S  Time-varying: none, drive-by, urban-walk, edge-of-cell, rlf-cycle"
      echo "  --interference-type T  DL interferer: none (default), cw, narrowband (narrowband implies --grc)"
      echo "  --interference-freq N  Interferer freq offset from DC in Hz (default: 1e6)"
      echo "  --sir N       Signal-to-Interference Ratio in dB (default: 20, lower=stronger)"
      echo "  --iperf-bitrate N      UL iperf3 bitrate (default: 10M, e.g. 25M)"
      echo "  --iperf-dl-bitrate N   DL iperf3 bitrate (default: 5M, e.g. 12M)"
      exit 0 ;;
    *) warn "Unknown flag: $1" ;;
  esac
  shift
done

# ── Helpers ──────────────────────────────────────────────────────────────────
sudoc() { echo "$SUDO_PASS" | sudo -S "$@"; }

wait_for_process() {
  local name="$1" pattern="$2" timeout="${3:-15}"
  for i in $(seq 1 "$timeout"); do
    if pgrep -f "$pattern" &>/dev/null; then
      ok "$name is running (PID $(pgrep -f "$pattern" | head -1))"
      return 0
    fi
    sleep 1
  done
  fail "$name did not start within ${timeout}s"
}

wait_for_port() {
  local name="$1" port="$2" proto="${3:-tcp}" timeout="${4:-15}"
  for i in $(seq 1 "$timeout"); do
    if ss -lnp 2>/dev/null | grep -q ":${port} "; then
      ok "$name is listening on $proto/$port"
      return 0
    fi
    sleep 1
  done
  fail "$name did not open port $port within ${timeout}s"
}

wait_for_file() {
  local name="$1" path="$2" timeout="${3:-20}"
  for i in $(seq 1 "$timeout"); do
    if [[ -e "$path" ]]; then
      ok "$name exists: $path"
      return 0
    fi
    sleep 1
  done
  fail "$name ($path) did not appear within ${timeout}s"
}

kill_if_running() {
  local pattern="$1"
  if pgrep -f "$pattern" &>/dev/null; then
    warn "Killing leftover: $pattern"
    pkill -9 -f "$pattern" 2>/dev/null || true
    sleep 1
  fi
}

# ── Pre-flight cleanup ──────────────────────────────────────────────────────
info "Cleaning up any previous run..."
kill_if_running "srsue"
sudoc pkill -9 -f "ping.*10.45.0.1" 2>/dev/null || true
kill_if_running "telemetry_to_influxdb"
kill_if_running "grafana.*server.*grafana.ini"
kill_if_running "decoder run"
kill_if_running "srsran_reverse_proxy"
sudoc pkill -9 gnb 2>/dev/null || true
kill_if_running "zmq_channel_broker"
kill_if_running "srsran_channel_broker"
kill_if_running "jrtc$"
sleep 2
rm -f /tmp/jbpf/* 2>/dev/null || true
ok "Cleanup done"

# ── Source environment ───────────────────────────────────────────────────────
info "Sourcing environment from $JRTC_APPS_DIR/set_vars.sh ..."
# Ensure LD_LIBRARY_PATH is set before sourcing (setup_jrtc_env.sh appends to it)
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
# shellcheck disable=SC1091
source "$JRTC_APPS_DIR/set_vars.sh"
export PATH="$PATH:$JRTC_DIR/out/bin"
ok "Environment ready (JBPF_CODELETS=$JBPF_CODELETS)"

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Starting MAC Telemetry Pipeline${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Compute total steps for progress display
TOTAL_STEPS=7
$START_BROKER || TOTAL_STEPS=6
$START_GRAFANA && TOTAL_STEPS=$((TOTAL_STEPS + 1))
STEP=0
next_step() { STEP=$((STEP + 1)); }

# ── Step 1: jrt-controller ──────────────────────────────────────────────────
next_step
info "[$STEP/$TOTAL_STEPS] Starting jrt-controller..."
"$JRTC_BIN" 2>"$LOG_JRTC" &
wait_for_process "jrtc" "jrtc$" 10

# ── Step 2: ZMQ Channel Broker (optional) ────────────────────────────────────
if $START_BROKER; then
  next_step
  BROKER_ARGS="--snr $ZMQ_BROKER_SNR"
  BROKER_DESC="SNR=${ZMQ_BROKER_SNR} dB"
  if $ZMQ_BROKER_FADING; then
    BROKER_ARGS="$BROKER_ARGS --fading --doppler $ZMQ_BROKER_DOPPLER --k-factor $ZMQ_BROKER_K_FACTOR"
    if [ "$ZMQ_BROKER_K_FACTOR" -eq -100 ] 2>/dev/null; then
      BROKER_DESC="$BROKER_DESC, Rayleigh fd=${ZMQ_BROKER_DOPPLER} Hz"
    else
      BROKER_DESC="$BROKER_DESC, Rician K=${ZMQ_BROKER_K_FACTOR} dB fd=${ZMQ_BROKER_DOPPLER} Hz"
    fi
  fi
  if $USE_GRC_BROKER; then
    BROKER_ARGS="$BROKER_ARGS --profile $ZMQ_BROKER_PROFILE"
    BROKER_ARGS="$BROKER_ARGS --cfo $ZMQ_BROKER_CFO --drop-prob $ZMQ_BROKER_DROP"
    BROKER_ARGS="$BROKER_ARGS --scenario $ZMQ_BROKER_SCENARIO"
    [ "$ZMQ_BROKER_INTF_TYPE" != "none" ] && \
      BROKER_ARGS="$BROKER_ARGS --interference-type $ZMQ_BROKER_INTF_TYPE --interference-freq $ZMQ_BROKER_INTF_FREQ --sir $ZMQ_BROKER_SIR"
    if $ZMQ_BROKER_FADING && [ "$ZMQ_BROKER_K_FACTOR" -eq -100 ] 2>/dev/null; then
      BROKER_ARGS="$BROKER_ARGS --rayleigh"
    fi
    BROKER_DESC="$BROKER_DESC [GRC, profile=$ZMQ_BROKER_PROFILE"
    [ "$ZMQ_BROKER_CFO" != "0" ] && BROKER_DESC="$BROKER_DESC, cfo=${ZMQ_BROKER_CFO}Hz"
    [ "$ZMQ_BROKER_DROP" != "0" ] && BROKER_DESC="$BROKER_DESC, drop=${ZMQ_BROKER_DROP}"
    [ "$ZMQ_BROKER_SCENARIO" != "none" ] && BROKER_DESC="$BROKER_DESC, scenario=$ZMQ_BROKER_SCENARIO"
    [ "$ZMQ_BROKER_INTF_TYPE" != "none" ] && BROKER_DESC="$BROKER_DESC, interf=${ZMQ_BROKER_INTF_TYPE} SIR=${ZMQ_BROKER_SIR}dB"
    BROKER_DESC="$BROKER_DESC]"
    info "[$STEP/$TOTAL_STEPS] Starting GNU Radio channel broker ($BROKER_DESC)..."
    if $USE_GUI; then
      # GUI mode: no setsid (keep X11 session), explicit DISPLAY, no log redirect
      DISPLAY="${DISPLAY:-:0}" python3 -u "$GRC_BROKER_SCRIPT" $BROKER_ARGS &
    else
      setsid python3 -u "$GRC_BROKER_SCRIPT" $BROKER_ARGS --no-gui >/tmp/zmq_broker.log 2>&1 &
    fi
    sleep 2
    wait_for_process "GRC broker" "srsran_channel_broker" 8
    # Write a restart script so the watchdog can restart the broker without env vars
    cat > /tmp/restart_broker.sh << RESTART_EOF
#!/bin/bash
pkill -9 -f "srsran_channel_broker.py" 2>/dev/null || true
pkill -9 -f "zmq_channel_broker" 2>/dev/null || true
sleep 2
setsid python3 -u "$GRC_BROKER_SCRIPT" $BROKER_ARGS --no-gui >>/tmp/zmq_broker.log 2>&1 &
sleep 3
RESTART_EOF
    chmod +x /tmp/restart_broker.sh
  else
    [ "$ZMQ_BROKER_INTF_TYPE" != "none" ] && \
      BROKER_ARGS="$BROKER_ARGS --interference-type $ZMQ_BROKER_INTF_TYPE --interference-freq $ZMQ_BROKER_INTF_FREQ --sir $ZMQ_BROKER_SIR"
    info "[$STEP/$TOTAL_STEPS] Starting ZMQ channel broker ($BROKER_DESC)..."
    setsid $ZMQ_BROKER_BIN $BROKER_ARGS >/tmp/zmq_broker.log 2>&1 &
    sleep 1
    wait_for_process "ZMQ broker" "zmq_channel_broker" 5
    # Write a restart script so the watchdog can restart the broker without env vars
    cat > /tmp/restart_broker.sh << RESTART_EOF
#!/bin/bash
pkill -9 -f "srsran_channel_broker.py" 2>/dev/null || true
pkill -9 -f "zmq_channel_broker" 2>/dev/null || true
sleep 2
setsid $ZMQ_BROKER_BIN $BROKER_ARGS >>/tmp/zmq_broker.log 2>&1 &
sleep 3
RESTART_EOF
    chmod +x /tmp/restart_broker.sh
  fi
else
  info "Skipping ZMQ broker (--no-broker → perfect channel)"
  # When running without broker, gNB must talk directly to UE on ports 2000/2001.
  # Override the config on the fly via a temp file.
  GNB_CFG_ORIG="$GNB_CFG"
  GNB_CFG="/tmp/gnb_zmq_jbpf_nobroker.yml"
  sed 's|tx_port=tcp://127.0.0.1:4000|tx_port=tcp://127.0.0.1:2000|;s|rx_port=tcp://127.0.0.1:4001|rx_port=tcp://127.0.0.1:2001|' \
    "$GNB_CFG_ORIG" > "$GNB_CFG"
fi

# ── Step 3: gNB ─────────────────────────────────────────────────────────────
next_step
if $START_BROKER; then
  info "[$STEP/$TOTAL_STEPS] Starting gNB (ports 4000/4001 via broker)..."
else
  info "[$STEP/$TOTAL_STEPS] Starting gNB (ports 2000/2001 direct)..."
fi
sudoc "$GNB_BIN" -c "$GNB_CFG" 2>"$LOG_GNB" &
sleep 2
wait_for_file "IPC socket" "$IPC_SOCKET" 20

# Fix socket permissions so reverse proxy (non-root) can connect
sudoc chmod 777 "$IPC_SOCKET"
ok "IPC socket permissions fixed"

# Verify gNB started successfully
if grep -q "gNB started" "$LOG_GNB" 2>/dev/null; then
  ok "gNB started and connected to AMF"
else
  # Give it a few more seconds
  sleep 5
  if grep -q "gNB started" "$LOG_GNB" 2>/dev/null; then
    ok "gNB started and connected to AMF"
  else
    warn "gNB may not be fully ready — check $LOG_GNB"
  fi
fi

# ── Step 4: Reverse Proxy ───────────────────────────────────────────────────
next_step
info "[$STEP/$TOTAL_STEPS] Starting reverse proxy (port $REVERSE_PROXY_PORT)..."
"$REVERSE_PROXY_BIN" \
  --host-port "$REVERSE_PROXY_PORT" \
  --address "$IPC_SOCKET" \
  >"$LOG_PROXY" 2>&1 &
wait_for_port "Reverse proxy" "$REVERSE_PROXY_PORT" tcp 10

# ── Step 5: Decoder (in its own terminal window) ────────────────────────────
next_step
info "[$STEP/$TOTAL_STEPS] Starting decoder in a new terminal window (gRPC $DECODER_GRPC_PORT, data UDP $DECODER_DATA_PORT)..."
xterm -title "MAC Telemetry Decoder" -geometry 160x40 -bg black -fg green -fa "Monospace" -fs 10 -e bash -c "
  export LD_LIBRARY_PATH=\"${LD_LIBRARY_PATH:-}\"
  export PATH=\"$PATH\"
  echo '══════════════════════════════════════════════════'
  echo '  MAC Telemetry Decoder  (Ctrl+C to stop)'
  echo '══════════════════════════════════════════════════'
  echo ''
  \"$JRTC_CTL_BIN\" decoder run --decoder-data-enabled 2>&1 | tee \"$LOG_DECODER\"
  echo ''
  echo 'Decoder exited. Press Enter to close.'
  read
" &
wait_for_port "Decoder gRPC" "$DECODER_GRPC_PORT" tcp 10

# ── Step 6: Load codelets ───────────────────────────────────────────────────
next_step
info "[$STEP/$TOTAL_STEPS] Loading all codelet sets..."

# List of codelet sets to load (YAML config relative to JBPF_CODELETS)
CODELET_SETS=(
  "mac/mac_stats.yaml"                          # MAC scheduler: CRC, BSR, PHR, UCI, HARQ DL/UL (10 codelets)
  "rlc/rlc_stats.yaml"                          # RLC layer: DL/UL PDU, SDU, retx (11 codelets)
  "pdcp/pdcp_stats.yaml"                        # PDCP layer: DL/UL data/control PDUs (10 codelets)
  "fapi_ul_crc/fapi_gnb_crc_stats.yaml"         # FAPI CRC indication: PHY-level CRC (2 codelets)
  "fapi_dl_conf/fapi_gnb_dl_config_stats.yaml"  # FAPI DL TTI: DL scheduling per RNTI (2 codelets)
  "fapi_ul_conf/fapi_gnb_ul_config_stats.yaml"  # FAPI UL TTI: UL scheduling per RNTI (2 codelets)
  "fapi_rach/fapi_gnb_rach_stats.yaml"          # FAPI RACH: timing advance + power (2 codelets)
  "rrc/rrc.yaml"                                # RRC: UE add/remove/procedure/update (5 codelets)
  "ue_contexts/ue_contexts.yaml"                # UE contexts: DU/CU-CP/E1AP lifecycle (9 codelets)
  "ngap/ngap.yaml"                              # NGAP: procedure start/complete/reset (3 codelets)
  "perf/jbpf_stats.yaml"                        # jbpf perf: internal stats (1 codelet)
)

LOADED=0
FAILED=0
for CSET in "${CODELET_SETS[@]}"; do
  CSET_PATH="${JBPF_CODELETS}/${CSET}"
  CSET_NAME=$(basename "$CSET" .yaml)
  if [ ! -f "$CSET_PATH" ]; then
    warn "Codelet config not found: $CSET_PATH — skipping"
    FAILED=$((FAILED + 1))
    continue
  fi
  LOAD_OUTPUT=$("$JRTC_CTL_BIN" jbpf load \
    --config "$CSET_PATH" \
    --device-id 1 \
    --decoder-enable \
    --decoder-port "$DECODER_GRPC_PORT" \
    --jbpf-port "$REVERSE_PROXY_PORT" \
    2>&1) || {
      warn "Failed to load $CSET_NAME: $LOAD_OUTPUT"
      FAILED=$((FAILED + 1))
      continue
    }
  LOADED=$((LOADED + 1))
done
if [ $FAILED -eq 0 ]; then
  ok "All ${#CODELET_SETS[@]} codelet sets loaded successfully ($LOADED sets, ~60 codelets)"
else
  warn "Loaded $LOADED/${#CODELET_SETS[@]} codelet sets ($FAILED failed)"
fi

# ── Write comprehensive watchdog recovery script ─────────────────────────────
# Now that all variables are known (broker args, gNB paths, codelet paths),
# write /tmp/restart_broker.sh with a full pipeline recovery sequence:
# broker + gNB + reverse proxy + codelets.  The watchdog calls this
# synchronously before restarting srsUE, so it blocks until everything is ready.
if $START_BROKER; then
  # Build space-separated list of expanded codelet paths for the restart script
  _CODELET_PATH_LIST=""
  for _CSET in "${CODELET_SETS[@]}"; do
    _CODELET_PATH_LIST="$_CODELET_PATH_LIST ${JBPF_CODELETS}/${_CSET}"
  done

  if $USE_GRC_BROKER; then
    _BROKER_START="setsid python3 -u \"$GRC_BROKER_SCRIPT\" $BROKER_ARGS --no-gui >>/tmp/zmq_broker.log 2>&1 &"
  else
    _BROKER_START="setsid $ZMQ_BROKER_BIN $BROKER_ARGS >>/tmp/zmq_broker.log 2>&1 &"
  fi

  cat > /tmp/restart_broker.sh << RESTART_EOF
#!/bin/bash
# Full pipeline recovery — generated by launch_mac_telemetry.sh
# Restarts: broker → gNB → reverse proxy → codelets
# Called by ue_watchdog.sh before restarting srsUE after a drop.
sudoc() { echo "$SUDO_PASS" | sudo -S "\$@" 2>/dev/null; }
rlog() { echo "[\$(date '+%H:%M:%S')] [RESTART] \$*" | tee -a /tmp/restart_pipeline.log; }

rlog "=== Pipeline recovery start ==="

# 1. Stop processes that hold state (reverse proxy holds IPC socket fd, gNB holds ZMQ queue)
rlog "Stopping reverse proxy, gNB, broker..."
sudoc pkill -9 -f "srsran_reverse_proxy" 2>/dev/null || true
sudoc pkill -9 gnb 2>/dev/null || true
pkill -9 -f "srsran_channel_broker.py" 2>/dev/null || true
pkill -9 -f "zmq_channel_broker" 2>/dev/null || true
sleep 3

# 2. Start broker (must be up before gNB connects)
rlog "Starting ZMQ broker..."
$_BROKER_START
sleep 4

# 3. Start gNB (connects to broker on startup)
rlog "Starting gNB..."
# Remove stale IPC socket (kill-9 leaves it behind); wait loop needs a fresh one
sudoc rm -f "$IPC_SOCKET" 2>/dev/null || true
sudoc "$GNB_BIN" -c "$GNB_CFG" 2>>"$LOG_GNB" &
# Wait for new IPC socket (up to 25s)
for _i in \$(seq 1 25); do
    [ -S "$IPC_SOCKET" ] && break
    sleep 1
done
sudoc chmod 777 "$IPC_SOCKET" 2>/dev/null || true
rlog "IPC socket ready"

# 4. Start reverse proxy
rlog "Starting reverse proxy..."
"$REVERSE_PROXY_BIN" --host-port $REVERSE_PROXY_PORT --address "$IPC_SOCKET" >>"$LOG_PROXY" 2>&1 &
sleep 4

# 5. Reload all codelets (jBPF programs live in gNB — lost on gNB restart)
rlog "Loading codelets..."
for _cset_path in $_CODELET_PATH_LIST; do
    "$JRTC_CTL_BIN" jbpf load --config "\$_cset_path" --device-id 1 \
        --decoder-enable --decoder-port $DECODER_GRPC_PORT \
        --jbpf-port $REVERSE_PROXY_PORT >>/tmp/restart_pipeline.log 2>&1 || true
done
rlog "=== Pipeline recovery complete — watchdog will now start srsUE ==="
RESTART_EOF
  chmod +x /tmp/restart_broker.sh
  ok "Watchdog recovery script written (/tmp/restart_broker.sh — full gNB+broker+proxy+codelets)"
fi

# ── Step 7: UE + Traffic ────────────────────────────────────────────────────
if $START_UE; then
  next_step
  info "[$STEP/$TOTAL_STEPS] Starting srsUE..."
  sudoc ip netns add ue1 2>/dev/null || true
  sudoc "$SRSUE_BIN" "$UE_CONF" >"${LOG_DIR}/ue_stdout.log" 2>&1 &
  
  # Wait for TUN interface to come up (direct check — reliable regardless of log format)
  info "Waiting for UE to attach (up to 120s)..."
  UE_IP=""
  for i in $(seq 1 120); do
    UE_IP=$(sudoc ip netns exec ue1 ip -4 addr show tun_srsue 2>/dev/null \
            | grep -oP 'inet \K[\d.]+' || true)
    if [ -n "$UE_IP" ]; then
      break
    fi
    sleep 1
  done

  if [ -n "$UE_IP" ]; then
    ok "UE attached (IP: $UE_IP)"
  else
    UE_IP="unknown"
    warn "UE may not be fully attached yet — check $LOG_UE"
  fi

  if $START_TRAFFIC; then
    info "Starting iperf3 server on $IPERF_TARGET:$IPERF_PORT..."
    iperf3 -s -B "$IPERF_TARGET" -p "$IPERF_PORT" -D 2>/dev/null
    sleep 1
    if ss -lntp | grep -q ":$IPERF_PORT"; then
      ok "iperf3 server listening"
    else
      warn "iperf3 server may not have started — check manually"
    fi

    # Only start iperf3 client if TUN interface is up
    if [ "$UE_IP" != "unknown" ]; then
      info "Starting iperf3 UDP uplink ($IPERF_BITRATE for ${IPERF_DURATION}s)..."
      sudoc ip netns exec ue1 iperf3 -c "$IPERF_TARGET" -p "$IPERF_PORT" \
        -u -b "$IPERF_BITRATE" -t "$IPERF_DURATION" -l "$IPERF_PKT_LEN" \
        >/tmp/iperf3.log 2>&1 &
      ok "iperf3 UL traffic running in background (log: /tmp/iperf3.log)"

      # DL iperf3 (reverse mode): server at 10.45.0.1:5202 pushes to UE client
      iperf3 -s -B "$IPERF_TARGET" -p "$IPERF_DL_PORT" -D 2>/dev/null
      sleep 1
      sudoc ip netns exec ue1 iperf3 -c "$IPERF_TARGET" -p "$IPERF_DL_PORT" \
        -u -b "$IPERF_DL_BITRATE" -t "$IPERF_DURATION" -l "$IPERF_PKT_LEN" --reverse \
        >/tmp/iperf3_dl.log 2>&1 &
      ok "iperf3 DL traffic running (${IPERF_DL_BITRATE} reverse, log: /tmp/iperf3_dl.log)"

      # Continuous ICMP ping for RTT monitoring
      > "$PING_LOG"
      sudoc ip netns exec ue1 ping -i 1 "$IPERF_TARGET" >>"$PING_LOG" 2>&1 &
      ok "Ping RTT monitoring: UE → $IPERF_TARGET (log: $PING_LOG)"
    else
      warn "Skipping iperf3 client — TUN interface not ready. Start manually:"
      warn "  sudo ip netns exec ue1 iperf3 -c $IPERF_TARGET -p $IPERF_PORT -u -b $IPERF_BITRATE -t $IPERF_DURATION -l $IPERF_PKT_LEN &"
    fi
  fi
else
  next_step
  info "[$STEP/$TOTAL_STEPS] Skipping UE (--no-ue flag)"
fi

# ── UE Watchdog (restarts UE + traffic if TUN drops) ─────────────────────────
if $START_UE && $START_WATCHDOG; then
  export SUDO_PASS SRSUE_BIN UE_CONF LOG_DIR
  export IPERF_TARGET IPERF_PORT IPERF_DL_PORT
  export IPERF_BITRATE IPERF_DL_BITRATE IPERF_DURATION IPERF_PKT_LEN
  export PING_LOG START_TRAFFIC
  export USE_GRC_BROKER GRC_BROKER_SCRIPT ZMQ_BROKER_BIN BROKER_ARGS START_BROKER
  bash "$HOME/Desktop/ue_watchdog.sh" >>/tmp/ue_watchdog.log 2>&1 &
  ok "UE watchdog running (PID $!, log: /tmp/ue_watchdog.log)"
fi

# ── Step N: Grafana Dashboard (optional) ─────────────────────────────────────
if $START_GRAFANA; then
  next_step
  info "[$STEP/$TOTAL_STEPS] Starting Grafana + InfluxDB telemetry dashboard..."

  # Ensure InfluxDB is running
  if ! systemctl is-active --quiet influxdb 2>/dev/null; then
    info "Starting InfluxDB..."
    sudoc systemctl start influxdb
    sleep 2
  fi

  # Create database if needed
  curl -s -XPOST "http://${INFLUXDB_HOST}:${INFLUXDB_PORT}/query" \
    --data-urlencode "q=CREATE DATABASE ${INFLUXDB_DB}" >/dev/null 2>&1

  # Start Grafana
  if ! pgrep -f "grafana.*server.*grafana.ini" &>/dev/null; then
    (cd "$GRAFANA_DIR" && setsid ./bin/grafana server \
      --config grafana.ini \
      --homepath . \
      >/tmp/grafana.log 2>&1 &)
    sleep 3
    if curl -s http://localhost:3000/api/health | grep -q '"database":"ok"'; then
      ok "Grafana running at http://localhost:3000 (admin/admin)"
    else
      warn "Grafana may not be fully ready — check /tmp/grafana.log"
    fi
  else
    ok "Grafana already running"
  fi

  # Start telemetry ingestor (tail decoder log → InfluxDB)
  if ! pgrep -f "telemetry_to_influxdb" &>/dev/null; then
    PYTHONUNBUFFERED=1 python3 "$INGESTOR_SCRIPT" \
      --log "$LOG_DECODER" \
      --db "$INFLUXDB_DB" \
      --host "$INFLUXDB_HOST" \
      --port "$INFLUXDB_PORT" \
      --from-beginning \
      >/tmp/ingestor.log 2>&1 &
    sleep 1
    if pgrep -f "telemetry_to_influxdb" &>/dev/null; then
      ok "InfluxDB ingestor running (PID $(pgrep -f 'telemetry_to_influxdb' | head -1))"
    else
      warn "Ingestor may not have started — check /tmp/ingestor.log"
    fi
  else
    ok "Ingestor already running"
  fi

  # Start UE traffic ingestor (iperf3 UL/DL + ping → InfluxDB)
  if $START_UE && ! pgrep -f "ue_traffic_ingestor" &>/dev/null; then
    PYTHONUNBUFFERED=1 python3 "$HOME/Desktop/ue_traffic_ingestor.py" \
      --ul /tmp/iperf3.log \
      --dl /tmp/iperf3_dl.log \
      --ping "$PING_LOG" \
      --db "$INFLUXDB_DB" \
      --host "$INFLUXDB_HOST" \
      --port "$INFLUXDB_PORT" \
      >/tmp/traffic_ingestor.log 2>&1 &
    sleep 1
    if pgrep -f "ue_traffic_ingestor" &>/dev/null; then
      ok "UE traffic ingestor running (PID $(pgrep -f 'ue_traffic_ingestor' | head -1))"
    else
      warn "UE traffic ingestor may not have started — check /tmp/traffic_ingestor.log"
    fi
  fi
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Pipeline is UP!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
pid_of() { pgrep -f "$1" 2>/dev/null | head -1 || echo '?'; }
echo "  Components:"
echo "    jrtc            PID $(pid_of 'jrtc$')"
if $START_BROKER; then
  BROKER_STATUS="SNR=${ZMQ_BROKER_SNR} dB"
  if $ZMQ_BROKER_FADING; then
    if [ "$ZMQ_BROKER_K_FACTOR" -eq -100 ] 2>/dev/null; then
      BROKER_STATUS="$BROKER_STATUS, Rayleigh fd=${ZMQ_BROKER_DOPPLER} Hz"
    else
      BROKER_STATUS="$BROKER_STATUS, Rician K=${ZMQ_BROKER_K_FACTOR} dB fd=${ZMQ_BROKER_DOPPLER} Hz"
    fi
  fi
  if $USE_GRC_BROKER; then
    BROKER_STATUS="$BROKER_STATUS [GRC, profile=$ZMQ_BROKER_PROFILE]"
    echo "    GRC broker      PID $(pid_of 'srsran_channel_broker')   ($BROKER_STATUS)"
  else
    echo "    ZMQ broker      PID $(pid_of 'zmq_channel_broker')   ($BROKER_STATUS)"
  fi
else
  echo "    ZMQ broker      (disabled — perfect channel)"
fi
echo "    gNB             PID $(pid_of 'gnb')"
echo "    Reverse proxy   PID $(pid_of 'srsran_reverse_proxy')   (port $REVERSE_PROXY_PORT)"
echo "    Decoder         PID $(pid_of 'decoder run')   (gRPC $DECODER_GRPC_PORT, data UDP $DECODER_DATA_PORT)"
echo "    Codelets        $LOADED/${#CODELET_SETS[@]} sets loaded"
$START_UE && echo "    srsUE           PID $(pid_of 'srsue')" || true
$START_UE && $START_WATCHDOG && echo "    UE watchdog     PID $(pid_of 'ue_watchdog.sh')" || true
if $START_GRAFANA; then
  echo "    Grafana         PID $(pid_of 'grafana.*server')   (http://localhost:3000)"
  echo "    Ingestor        PID $(pid_of 'telemetry_to_influxdb')"
fi
echo ""
echo "  Log files:"
echo "    jrtc:    $LOG_JRTC"
echo "    gNB:     $LOG_GNB"
echo "    Proxy:   $LOG_PROXY"
echo "    Decoder: $LOG_DECODER"
$START_UE && echo "    UE:      $LOG_UE" || true
$START_UE && $START_TRAFFIC && echo "    UL:      /tmp/iperf3.log" || true
$START_UE && $START_TRAFFIC && echo "    DL:      /tmp/iperf3_dl.log" || true
$START_UE && $START_TRAFFIC && echo "    Ping:    $PING_LOG" || true
$START_UE && $START_WATCHDOG && echo "    Watchdog:/tmp/ue_watchdog.log" || true
$START_BROKER && echo "    Broker:  /tmp/zmq_broker.log" || true
$START_GRAFANA && echo "    Grafana: /tmp/grafana.log" || true
$START_GRAFANA && echo "    Ingest:  /tmp/ingestor.log" || true
$START_GRAFANA && $START_UE && echo "    Traffic: /tmp/traffic_ingestor.log" || true
echo ""
echo "  View live telemetry:"
echo "    tail -f $LOG_DECODER"
if $START_GRAFANA; then
  echo ""
  echo "  Grafana Dashboard:"
  echo "    http://localhost:3000/d/srsran-5g-nr-telemetry/srsran-5g-nr-telemetry"
  echo "    Login: admin / admin"
fi
echo ""
echo "  Stop everything:"
echo "    ~/Desktop/stop_mac_telemetry.sh"
echo ""
