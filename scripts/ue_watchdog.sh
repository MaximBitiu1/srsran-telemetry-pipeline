#!/usr/bin/env bash
# =============================================================================
#  srsUE Watchdog — auto-restarts UE + traffic when TUN interface drops
#
#  Launched by launch_mac_telemetry.sh as a background process.
#  All config is passed via environment variables.
#
#  Required env vars (set by launch_mac_telemetry.sh):
#    SUDO_PASS, SRSUE_BIN, UE_CONF, LOG_DIR
#    IPERF_TARGET, IPERF_PORT, IPERF_DL_PORT
#    IPERF_BITRATE, IPERF_DL_BITRATE, IPERF_DURATION, IPERF_PKT_LEN
#    PING_LOG, START_TRAFFIC
# =============================================================================

WATCHDOG_LOG="${LOG_DIR:-/tmp}/ue_watchdog.log"
MAX_RETRIES=10          # give up after this many consecutive restarts
CHECK_INTERVAL=5        # seconds between TUN checks
ATTACH_TIMEOUT=45       # seconds to wait for UE to re-attach
TUN_TIMEOUT=30          # seconds to wait for TUN to come up after PDU session

sudoc() { echo "$SUDO_PASS" | sudo -S "$@" 2>/dev/null; }

log()  { echo "[$(date '+%H:%M:%S')] [WATCHDOG] $*" | tee -a "$WATCHDOG_LOG"; }
logw() { echo "[$(date '+%H:%M:%S')] [WATCHDOG][WARN] $*" | tee -a "$WATCHDOG_LOG"; }

tun_up() {
    # srsue process must be alive
    pgrep -f "srsue" > /dev/null 2>&1 || return 1
    # If UE log shows GW fatal error, the PDU session is dead
    grep -q "Fatal Error: Couldn't allocate PDU" "${LOG_DIR}/ue.log" 2>/dev/null && return 1
    # Primary check: TUN interface via sudo
    if sudoc ip netns exec ue1 ip link show tun_srsue 2>/dev/null | grep -q "UP"; then
        # Data-plane check: verify traffic can actually flow (catches SFN-desynced UE)
        # Skip for first 60s of uptime — data plane needs time to stabilize after attach
        # Run every ~30s after that to avoid adding latency on every 5s poll
        local now; now=$(date +%s)
        local up_secs=$(( now - UP_SINCE ))
        if [ "$up_secs" -ge 60 ] && [ $(( now % 30 )) -lt "$CHECK_INTERVAL" ]; then
            if ! sudoc ip netns exec ue1 ping -c 2 -W 2 "${IPERF_TARGET:-10.45.0.1}" > /dev/null 2>&1; then
                logw "TUN is UP but ping to ${IPERF_TARGET:-10.45.0.1} failed — data plane broken (SFN desync?)"
                return 1
            fi
        fi
        return 0
    fi
    # Fallback: check UE log for RLC/RRC release (connection dropped)
    grep -qE "rrcRelease|UEContextRelease|PDU session released" "${LOG_DIR}/ue.log" 2>/dev/null && return 1
    return 1
}

get_ue_ip() {
    sudoc ip netns exec ue1 ip -4 addr show tun_srsue 2>/dev/null \
        | grep -oP 'inet \K[\d.]+'
}

kill_ue_and_traffic() {
    sudoc pkill -9 -f "srsue" 2>/dev/null || true
    sudoc pkill -9 -f "ip netns exec ue1 iperf3" 2>/dev/null || true
    sudoc pkill -9 -f "ip netns exec ue1 ping" 2>/dev/null || true
    sleep 2
}

restart_broker() {
    [ -x /tmp/restart_broker.sh ] || return 0
    log "Restarting ZMQ broker to reset ZMQ state..."
    bash /tmp/restart_broker.sh
    log "Broker restarted"
}

start_ue() {
    log "Starting srsUE..."
    # Remove old UE log (owned by root) so srsUE creates a fresh one on start
    sudoc rm -f "${LOG_DIR}/ue.log" 2>/dev/null || true
    # Write stdout to a fresh user-owned file (not the root-owned internal log)
    sudoc "$SRSUE_BIN" "$UE_CONF" > /tmp/ue_restart.log 2>&1 &

    # Wait for TUN interface to come up — direct check, no log grepping
    UE_IP=""
    local total_wait=$((ATTACH_TIMEOUT + TUN_TIMEOUT))
    for i in $(seq 1 "$total_wait"); do
        UE_IP=$(get_ue_ip)
        if [ -n "$UE_IP" ]; then
            log "UE re-attached (IP: $UE_IP)"
            return 0
        fi
        sleep 1
    done

    logw "UE started but TUN not up after ${total_wait}s"
    return 1
}

start_traffic() {
    local ue_ip="$1"
    [ "$START_TRAFFIC" = "true" ] || return 0
    [ -n "$ue_ip" ] || return 0

    log "Restarting iperf3 UL (${IPERF_BITRATE} for ${IPERF_DURATION}s)..."
    sudoc ip netns exec ue1 iperf3 \
        -c "$IPERF_TARGET" -p "$IPERF_PORT" \
        -u -b "$IPERF_BITRATE" -t "$IPERF_DURATION" -l "$IPERF_PKT_LEN" \
        >> /tmp/iperf3.log 2>&1 &

    log "Restarting iperf3 DL (${IPERF_DL_BITRATE} reverse)..."
    sudoc ip netns exec ue1 iperf3 \
        -c "$IPERF_TARGET" -p "$IPERF_DL_PORT" \
        -u -b "$IPERF_DL_BITRATE" -t "$IPERF_DURATION" -l "$IPERF_PKT_LEN" --reverse \
        >> /tmp/iperf3_dl.log 2>&1 &

    log "Restarting ping RTT monitor..."
    sudoc ip netns exec ue1 ping -i 1 "$IPERF_TARGET" >> "$PING_LOG" 2>&1 &
}

# ── Main loop ────────────────────────────────────────────────────────────────
log "Watchdog started (max_retries=$MAX_RETRIES, check_interval=${CHECK_INTERVAL}s)"
RETRIES=0
UP_SINCE=0  # epoch when TUN last came up (used for ping grace period)
# Detect initial attach state — don't assume UE is up; check TUN directly
if [ -n "$(get_ue_ip)" ]; then
    WAS_UP=true
    UP_SINCE=$(date +%s)
    log "UE already attached at watchdog start"
else
    WAS_UP=false
    log "UE not yet attached at watchdog start — waiting for first attach"
fi

while true; do
    sleep "$CHECK_INTERVAL"

    if tun_up; then
        if ! $WAS_UP; then
            # First attach (or re-attach) detected
            UE_IP=$(get_ue_ip)
            log "UE first attach detected (IP: $UE_IP) — starting traffic"
            start_traffic "$UE_IP"
            UP_SINCE=$(date +%s)
        fi
        WAS_UP=true
        RETRIES=0    # reset retry count on sustained connection
        continue
    fi

    # TUN is down — only act if it was previously up (ignore startup period)
    if ! $WAS_UP; then
        continue
    fi

    RETRIES=$((RETRIES + 1))
    log "TUN interface down — UE dropped (attempt $RETRIES/$MAX_RETRIES)"

    if [ "$RETRIES" -gt "$MAX_RETRIES" ]; then
        logw "Max retries reached — watchdog exiting. Run stop_mac_telemetry.sh to clean up."
        exit 1
    fi

    kill_ue_and_traffic
    restart_broker

    if start_ue; then
        UE_IP=$(get_ue_ip)
        start_traffic "$UE_IP"
        WAS_UP=true
        UP_SINCE=$(date +%s)
    else
        logw "UE restart failed — will retry in ${CHECK_INTERVAL}s"
        # Leave WAS_UP=true so next loop detects TUN still down and retries
    fi
done
