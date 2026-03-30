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
TUN_TIMEOUT=15          # seconds to wait for TUN to come up after PDU session

sudoc() { echo "$SUDO_PASS" | sudo -S "$@" 2>/dev/null; }

log()  { echo "[$(date '+%H:%M:%S')] [WATCHDOG] $*" | tee -a "$WATCHDOG_LOG"; }
logw() { echo "[$(date '+%H:%M:%S')] [WATCHDOG][WARN] $*" | tee -a "$WATCHDOG_LOG"; }

tun_up() {
    # TUN must exist AND srsue process must be alive
    pgrep -f "srsue" > /dev/null 2>&1 || return 1
    sudoc ip netns exec ue1 ip link show tun_srsue 2>/dev/null | grep -q "UP"
}

get_ue_ip() {
    sudoc ip netns exec ue1 ip -4 addr show tun_srsue 2>/dev/null \
        | grep -oP 'inet \K[\d.]+'
}

kill_ue_and_traffic() {
    sudoc pkill -9 -f "srsue" 2>/dev/null || true
    sudoc pkill -9 -f "ip netns exec ue1 iperf3" 2>/dev/null || true
    sudoc pkill -9 -f "ip netns exec ue1 ping" 2>/dev/null || true
    sleep 1
}

start_ue() {
    log "Starting srsUE..."
    # Truncate UE log so PDU Session grep works cleanly on the new run
    > "${LOG_DIR}/ue.log"
    sudoc "$SRSUE_BIN" "$UE_CONF" >> "${LOG_DIR}/ue.log" 2>&1 &

    # Wait for PDU session
    for i in $(seq 1 "$ATTACH_TIMEOUT"); do
        if grep -q "PDU Session" "${LOG_DIR}/ue.log" 2>/dev/null; then
            break
        fi
        sleep 1
    done

    # Wait for TUN interface
    UE_IP=""
    for i in $(seq 1 "$TUN_TIMEOUT"); do
        UE_IP=$(get_ue_ip)
        if [ -n "$UE_IP" ]; then
            log "UE re-attached (IP: $UE_IP)"
            return 0
        fi
        sleep 1
    done

    logw "UE started but TUN not up after ${TUN_TIMEOUT}s"
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
WAS_UP=false

while true; do
    sleep "$CHECK_INTERVAL"

    if tun_up; then
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
    WAS_UP=false

    if start_ue; then
        UE_IP=$(get_ue_ip)
        start_traffic "$UE_IP"
        WAS_UP=true
    else
        logw "UE restart failed — will retry in ${CHECK_INTERVAL}s"
    fi
done
