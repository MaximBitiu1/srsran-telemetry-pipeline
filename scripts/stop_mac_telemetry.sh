#!/usr/bin/env bash
# =============================================================================
#  srsRAN jbpf MAC Telemetry — Teardown Script
#  Stops all components in reverse order and cleans up.
#
#  Usage:  ./stop_mac_telemetry.sh
# =============================================================================
set -uo pipefail

SUDO_PASS="2003"
JRTC_APPS_DIR="$HOME/Desktop/jrtc-apps"
JRTC_CTL_BIN="$HOME/Desktop/jrt-controller/out/bin/jrtc-ctl"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[  OK]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }

sudoc() { echo "$SUDO_PASS" | sudo -S "$@" 2>/dev/null; }

stop_proc() {
  local name="$1" pattern="$2" use_sudo="${3:-false}"
  if pgrep -f "$pattern" &>/dev/null; then
    info "Stopping $name..."
    if $use_sudo; then
      sudoc pkill -9 -f "$pattern" 2>/dev/null || true
    else
      pkill -9 -f "$pattern" 2>/dev/null || true
    fi
    sleep 1
    if pgrep -f "$pattern" &>/dev/null; then
      warn "$name still running — forcing kill"
      sudoc kill -9 "$(pgrep -f "$pattern" | head -1)" 2>/dev/null || true
      sleep 1
    fi
    if pgrep -f "$pattern" &>/dev/null; then
      warn "$name could not be stopped"
    else
      ok "$name stopped"
    fi
  else
    ok "$name was not running"
  fi
}

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Stopping MAC Telemetry Pipeline${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Unload codelets first (graceful) — only if proxy and gNB are both alive
if pgrep -f "srsran_reverse_proxy" &>/dev/null && pgrep -f "gnb" &>/dev/null; then
  info "Unloading codelets (graceful)..."
  export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
  # shellcheck disable=SC1091
  source "$JRTC_APPS_DIR/set_vars.sh" 2>/dev/null || true
  export PATH="$PATH:$(dirname "$JRTC_CTL_BIN")"
  "$JRTC_CTL_BIN" jbpf unload \
    --config "${JBPF_CODELETS:-$JRTC_APPS_DIR/codelets}/mac/mac_stats.yaml" \
    --device-id 1 \
    --jbpf-port 30450 \
    2>/dev/null && ok "Codelets unloaded" || warn "Codelet unload failed (non-critical)"
else
  info "Proxy/gNB not running — skipping codelet unload"
fi

# Stop in reverse order
stop_proc "iperf3"         "iperf3"             true
stop_proc "srsUE"          "srsue"              true
stop_proc "ingestor"       "telemetry_to_influxdb" false
stop_proc "Grafana"        "grafana.*server.*grafana.ini" false
stop_proc "decoder"        "decoder run"        false
stop_proc "reverse proxy"  "srsran_reverse_proxy" false
stop_proc "gNB"            "gnb"                true
stop_proc "ZMQ broker"    "zmq_channel_broker" false
stop_proc "GRC broker"    "srsran_channel_broker" false
stop_proc "jrtc"           "jrtc$"              false

# Clean up IPC sockets and temp files
info "Cleaning IPC sockets..."
rm -f /tmp/jbpf/* 2>/dev/null || true
rm -f /tmp/gnb_zmq_jbpf_nobroker.yml 2>/dev/null || true
ok "IPC sockets cleaned"

# Wait for ports to release
sleep 1
STUCK_PORTS=""
for p in 2000 2001 4000 4001; do
  if ss -lntp 2>/dev/null | grep -q ":$p "; then
    STUCK_PORTS="$STUCK_PORTS $p"
  fi
done
if [[ -n "$STUCK_PORTS" ]]; then
  warn "Ports still in use:$STUCK_PORTS — forcing release..."
  for p in $STUCK_PORTS; do
    sudoc fuser -k "$p/tcp" 2>/dev/null || true
  done
  sleep 1
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  All components stopped.${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
