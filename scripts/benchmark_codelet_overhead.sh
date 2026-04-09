#!/usr/bin/env bash
# =============================================================================
#  jBPF Codelet CPU Overhead Benchmark
#
#  Runs two 90-second experiments back-to-back:
#    Run A: gNB + UE + iperf3, NO codelets (hooks present but nothing attached)
#    Run B: gNB + UE + iperf3, ALL codelets loaded via jrtc
#
#  Measures per-process CPU (pidstat) and system-wide CPU (mpstat) for each run.
#  Writes results to /tmp/bench_*.csv and prints a summary table.
#
#  Usage: ./benchmark_codelet_overhead.sh
# =============================================================================

SUDO_PASS="2003"
SRSRAN_DIR="$HOME/Desktop/srsRAN_Project_jbpf"
JRTC_DIR="$HOME/Desktop/jrt-controller"
JRTC_APPS_DIR="$HOME/Desktop/jrtc-apps"
UE_CONF="$HOME/Desktop/ue_zmq.conf"
GRC_BROKER_SCRIPT="$HOME/Desktop/srsran_channel_broker.py"

GNB_BIN="$SRSRAN_DIR/build/apps/gnb/gnb"
GNB_CFG_ORIG="$SRSRAN_DIR/configs/gnb_zmq_jbpf.yml"
REVERSE_PROXY_BIN="$SRSRAN_DIR/out/bin/srsran_reverse_proxy"
JRTC_BIN="$JRTC_DIR/out/bin/jrtc"
JRTC_CTL_BIN="$JRTC_DIR/out/bin/jrtc-ctl"
SRSUE_BIN="/usr/local/bin/srsue"
IPC_SOCKET="/tmp/jbpf/jbpf_lcm_ipc"
REVERSE_PROXY_PORT=30450
DECODER_GRPC_PORT=20789

MEASURE_DURATION=90   # seconds of CPU measurement per run
STABILISE_WAIT=25     # seconds to wait after UE attaches before measuring

OUT_DIR="/tmp/bench_$$"
mkdir -p "$OUT_DIR"
LOG_GNB="$OUT_DIR/gnb.log"
LOG_UE="$OUT_DIR/ue.log"
LOG_PROXY="$OUT_DIR/proxy.log"
LOG_JRTC="$OUT_DIR/jrtc.log"

sudoc()       { echo "$SUDO_PASS" | sudo -S "$@" 2>/dev/null; }
log()         { echo "[$(date '+%H:%M:%S')] $*"; }
log_section() { echo; echo "══════════════════════════════════════════════"; echo "  $*"; echo "══════════════════════════════════════════════"; }

# ── Environment ──────────────────────────────────────────────────────────────
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
source "$JRTC_APPS_DIR/set_vars.sh"
export PATH="$PATH:$JRTC_DIR/out/bin"

CODELET_SETS=(
  "mac/mac_stats.yaml"
  "rlc/rlc_stats.yaml"
  "pdcp/pdcp_stats.yaml"
  "fapi_ul_crc/fapi_gnb_crc_stats.yaml"
  "fapi_dl_conf/fapi_gnb_dl_config_stats.yaml"
  "fapi_ul_conf/fapi_gnb_ul_config_stats.yaml"
  "fapi_rach/fapi_gnb_rach_stats.yaml"
  "rrc/rrc.yaml"
  "ue_contexts/ue_contexts.yaml"
  "ngap/ngap.yaml"
  "perf/jbpf_stats.yaml"
  "mac/mac_stats_custom.yaml"
)

# ── Helpers ───────────────────────────────────────────────────────────────────
cleanup() {
  log "Stopping all processes..."
  sudoc pkill -9 -f "srsue" 2>/dev/null || true
  sudoc pkill -9 gnb 2>/dev/null || true
  pkill -9 -f "srsran_reverse_proxy" 2>/dev/null || true
  pkill -9 -f "jrtc$" 2>/dev/null || true
  pkill -9 -f "jrtc-ctl" 2>/dev/null || true
  pkill -9 -f "srsran_channel_broker" 2>/dev/null || true
  pkill -9 -f "zmq_channel_broker" 2>/dev/null || true
  pkill -9 -f "iperf3" 2>/dev/null || true
  sudoc pkill -9 -f "ping.*10.45.0" 2>/dev/null || true
  # IPC socket is owned by root (created by gnb running as root) — must use sudo
  sudoc rm -f /tmp/jbpf/jbpf_lcm_ipc /tmp/jbpf/jrt_controller 2>/dev/null || true
  # Ensure jrtc (runs as user) can create its socket in this dir
  sudoc chmod 777 /tmp/jbpf 2>/dev/null || mkdir -p /tmp/jbpf && chmod 777 /tmp/jbpf
  sleep 3
}

start_jrtc() {
  log "Starting jrtc..."
  # jrtc must run before gNB — gNB connects to jrtc's IPC socket at JBPF init
  "$JRTC_BIN" >"$LOG_JRTC" 2>&1 &
  sleep 3
  # Verify jrtc created its IPC socket
  for i in $(seq 1 10); do
    pgrep -f "jrtc$" &>/dev/null && { log "jrtc running (PID=$(pgrep -f 'jrtc$'))"; return 0; }
    sleep 1
  done
  log "ERROR: jrtc did not start"; return 1
}

start_gnb_nobroker() {
  # Patch config to use direct ZMQ ports (no broker)
  local cfg="/tmp/gnb_bench_direct.yml"
  sed 's|tx_port=tcp://127.0.0.1:4000|tx_port=tcp://127.0.0.1:2000|;s|rx_port=tcp://127.0.0.1:4001|rx_port=tcp://127.0.0.1:2001|' \
    "$GNB_CFG_ORIG" > "$cfg"
  # Use sudo -E to preserve LD_LIBRARY_PATH; capture full output (stdout+stderr)
  echo "$SUDO_PASS" | sudo -SE env LD_LIBRARY_PATH="$LD_LIBRARY_PATH" \
    "$GNB_BIN" -c "$cfg" >"$LOG_GNB" 2>&1 &
  sleep 2
  log "gNB started (direct mode, PID=$(pgrep -f 'gnb -c' | head -1))"
}

wait_for_ipc() {
  log "Waiting for IPC socket..."
  for i in $(seq 1 30); do
    [ -e "$IPC_SOCKET" ] && { sudoc chmod 777 "$IPC_SOCKET"; log "IPC socket ready"; return 0; }
    sleep 1
  done
  log "ERROR: IPC socket did not appear"; return 1
}

start_ue() {
  sudoc ip netns add ue1 2>/dev/null || true
  sudoc "$SRSUE_BIN" "$UE_CONF" >"$LOG_UE" 2>&1 &
  log "srsUE started, waiting for attach (up to 90s)..."
  UE_IP=""
  for i in $(seq 1 90); do
    UE_IP=$(sudoc ip netns exec ue1 ip -4 addr show tun_srsue 2>/dev/null | grep -oP 'inet \K[\d.]+' || true)
    [ -n "$UE_IP" ] && { log "UE attached (IP: $UE_IP)"; return 0; }
    sleep 1
  done
  log "ERROR: UE did not attach"; return 1
}

start_traffic() {
  iperf3 -s -B 10.45.0.1 -p 5201 -D 2>/dev/null
  sleep 1
  sudoc ip netns exec ue1 iperf3 -c 10.45.0.1 -p 5201 \
    -u -b 10M -t $((MEASURE_DURATION + STABILISE_WAIT + 30)) -l 1400 \
    >/tmp/iperf3_bench.log 2>&1 &
  log "iperf3 UL traffic running (10 Mbps)"
}

measure_cpu() {
  local label="$1"
  local out_pidstat="$OUT_DIR/pidstat_${label}.csv"
  local out_mpstat="$OUT_DIR/mpstat_${label}.txt"

  # gnb binary runs as root child of the sudo wrapper; pgrep -x gnb finds it by comm
  GNB_PID=$(pgrep -x gnb 2>/dev/null | head -1)
  # fallback: find child of any sudo process that launched gnb
  if [ -z "$GNB_PID" ]; then
    SUDO_PID=$(pgrep -f 'sudo.*gnb -c' | head -1)
    [ -n "$SUDO_PID" ] && GNB_PID=$(ps --ppid "$SUDO_PID" -o pid= 2>/dev/null | head -1)
  fi
  JRTC_PID=$(pgrep -f 'jrtc$' | head -1 || echo "")

  log "Measuring CPU for ${MEASURE_DURATION}s (gNB PID=${GNB_PID:-NOT_FOUND}, jrtc PID=${JRTC_PID:-none})..."

  # Per-process: pidstat at 1s intervals (use LC_ALL=C to force dot decimal separator)
  local pid_arg="${GNB_PID:-1}"
  [ -n "$JRTC_PID" ] && pid_arg="${pid_arg},${JRTC_PID}"

  LC_ALL=C pidstat -p "$pid_arg" 1 "$MEASURE_DURATION" \
    | tee "$out_pidstat" &
  PIDSTAT_PID=$!

  # System-wide: mpstat at 1s intervals
  LC_ALL=C mpstat -P ALL 1 "$MEASURE_DURATION" > "$out_mpstat" &
  MPSTAT_PID=$!

  wait $PIDSTAT_PID $MPSTAT_PID
  log "CPU measurement complete → $out_pidstat, $out_mpstat"
}

load_codelets() {
  local loaded=0 failed=0
  for CSET in "${CODELET_SETS[@]}"; do
    local path="${JBPF_CODELETS}/${CSET}"
    [ ! -f "$path" ] && { log "WARN: $CSET not found, skipping"; failed=$((failed+1)); continue; }
    "$JRTC_CTL_BIN" jbpf load \
      --config "$path" \
      --device-id 1 \
      --decoder-enable \
      --decoder-port "$DECODER_GRPC_PORT" \
      --jbpf-port "$REVERSE_PROXY_PORT" \
      >/dev/null 2>&1 \
      && loaded=$((loaded+1)) \
      || { log "WARN: failed to load $CSET"; failed=$((failed+1)); }
  done
  log "Codelets: $loaded loaded, $failed failed"
}

# =============================================================================
log_section "Run A — codelets OFF (jrtc running, hooks present, zero codelets loaded)"
# =============================================================================
cleanup

start_jrtc
start_gnb_nobroker
wait_for_ipc

start_ue
start_traffic

log "Stabilising for ${STABILISE_WAIT}s before measurement..."
sleep "$STABILISE_WAIT"

measure_cpu "off"

cleanup

# =============================================================================
log_section "Run B — codelets ON (all 12 codelet sets, ~60 programs)"
# =============================================================================
cleanup

start_jrtc
start_gnb_nobroker
wait_for_ipc

log "Starting reverse proxy..."
"$REVERSE_PROXY_BIN" \
  --host-port "$REVERSE_PROXY_PORT" \
  --address "$IPC_SOCKET" \
  >"$LOG_PROXY" 2>&1 &
sleep 3

# Start decoder (silent, background)
"$JRTC_CTL_BIN" decoder run --decoder-data-enabled >/dev/null 2>&1 &
sleep 2

load_codelets

start_ue
start_traffic

log "Stabilising for ${STABILISE_WAIT}s before measurement..."
sleep "$STABILISE_WAIT"

measure_cpu "on"

cleanup

# =============================================================================
log_section "Results"
# =============================================================================
python3 - "$OUT_DIR" <<'PYEOF'
import sys, os, re
import statistics

d = sys.argv[1]

def parse_pidstat(path):
    """Return dict: cmd -> list of %cpu values. Normalises jrtc_main->jrtc, gnb*->gnb."""
    result = {}
    if not os.path.exists(path):
        return result
    with open(path) as f:
        for line in f:
            parts = line.split()
            # pidstat line: time uid pid %usr %sys %guest %wait %CPU CPU command
            if len(parts) >= 10 and re.match(r'\d+:\d+:\d+', parts[0]):
                try:
                    cpu = float(parts[7])   # %CPU column
                    cmd = parts[-1]
                    # Normalise process names
                    if cmd.startswith('jrtc'):
                        cmd = 'jrtc'
                    elif cmd.startswith('gnb'):
                        cmd = 'gnb'
                    result.setdefault(cmd, []).append(cpu)
                except (ValueError, IndexError):
                    pass
    return result

def parse_mpstat(path):
    """Return average idle% across all CPUs from the 'all' summary lines"""
    idles = []
    if not os.path.exists(path):
        return None
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 12 and 'all' in parts:
                try:
                    idle = float(parts[-1])
                    idles.append(idle)
                except ValueError:
                    pass
    return (100 - statistics.mean(idles)) if idles else None

off_pid = parse_pidstat(os.path.join(d, "pidstat_off.csv"))
on_pid  = parse_pidstat(os.path.join(d, "pidstat_on.csv"))
off_sys = parse_mpstat(os.path.join(d, "mpstat_off.txt"))
on_sys  = parse_mpstat(os.path.join(d, "mpstat_on.txt"))

print()
print("┌─────────────────────────────────────────────────────────────┐")
print("│                jBPF Codelet CPU Overhead                    │")
print("├──────────────────────────────┬──────────────┬───────────────┤")
print("│ Metric                       │  OFF         │  ON           │")
print("├──────────────────────────────┼──────────────┼───────────────┤")

def row(label, off_v, on_v, unit=""):
    o = f"{off_v:.2f}{unit}" if off_v is not None else "N/A"
    n = f"{on_v:.2f}{unit}"  if on_v  is not None else "N/A"
    print(f"│ {label:<28} │ {o:<12} │ {n:<13} │")

# gNB CPU
gnb_off = statistics.mean(off_pid.get('gnb', [0])) if off_pid.get('gnb') else None
gnb_on  = statistics.mean(on_pid.get('gnb',  [0])) if on_pid.get('gnb')  else None
row("gNB process CPU avg (%)", gnb_off, gnb_on, "%")

gnb_off_p99 = sorted(off_pid.get('gnb', [0]))[int(len(off_pid.get('gnb', [0]))*0.99)-1] if off_pid.get('gnb') else None
gnb_on_p99  = sorted(on_pid.get('gnb',  [0]))[int(len(on_pid.get('gnb',  [0]))*0.99)-1]  if on_pid.get('gnb')  else None
row("gNB process CPU p99 (%)", gnb_off_p99, gnb_on_p99, "%")

# jrtc CPU (only relevant in ON run)
jrtc_on = statistics.mean(on_pid.get('jrtc', [0])) if on_pid.get('jrtc') else 0.0
print(f"│ {'jrtc process CPU avg (%)':<28} │ {'n/a':<12} │ {jrtc_on:.2f}%{'':8} │")

# System-wide
row("System CPU used (all cores)", off_sys, on_sys, "%")

print("├──────────────────────────────┼──────────────┼───────────────┤")

# Delta
if gnb_off is not None and gnb_on is not None:
    delta_gnb = gnb_on - gnb_off
    delta_sys = (on_sys - off_sys) if (off_sys and on_sys) else None
    row("Delta gNB CPU (ON - OFF)", None, delta_gnb, "%")
    if delta_sys is not None:
        row("Delta system CPU (ON - OFF)", None, delta_sys, "%")
    print("└──────────────────────────────┴──────────────┴───────────────┘")
    print()
    print(f"  jBPF codelet overhead on gNB process: {delta_gnb:+.2f} percentage points")
    if delta_sys:
        print(f"  System-wide additional CPU used:      {delta_sys:+.2f} percentage points")
else:
    print("└──────────────────────────────┴──────────────┴───────────────┘")
    print()
    print("  Could not parse pidstat output. Check raw files in", d)

print()
print(f"  Raw data saved to: {d}/")
PYEOF

echo ""
echo "Benchmark complete. Raw files: $OUT_DIR/"
