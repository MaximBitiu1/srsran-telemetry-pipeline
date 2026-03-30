#!/usr/bin/env bash
# =============================================================================
#  Interference Sweep — tests CW and narrowband interference at multiple SIR
#  levels to find the boundary between stable and crashing channel.
#
#  Usage:
#    bash interference_sweep.sh [--duration N] [--settle N] [--output FILE]
#
#  Defaults:
#    --duration 90   seconds of measurement per test
#    --settle   30   seconds to wait for UE to attach before measuring
#    --output   /tmp/interference_sweep_results.txt
# =============================================================================
set -uo pipefail

DURATION=90
SETTLE=30
OUTPUT="/tmp/interference_sweep_results.txt"
BASE_SNR=28
BASE_K=3

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration) DURATION="$2"; shift 2 ;;
    --settle)   SETTLE="$2";   shift 2 ;;
    --output)   OUTPUT="$2";   shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

INFLUX="http://localhost:8086/query?db=srsran_telemetry"

# ── Helpers ──────────────────────────────────────────────────────────────────
log()  { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$OUTPUT"; }
hdr()  { echo "" | tee -a "$OUTPUT"; echo "══════════════════════════════════════════" | tee -a "$OUTPUT"; echo "  $*" | tee -a "$OUTPUT"; echo "══════════════════════════════════════════" | tee -a "$OUTPUT"; }

ue_alive() {
    pgrep -f srsue > /dev/null 2>&1 && \
    echo "2003" | sudo -S ip netns exec ue1 ip link show tun_srsue 2>/dev/null | grep -q "UP"
}

wait_for_ue() {
    local deadline=$((SECONDS + SETTLE + 30))
    while [ $SECONDS -lt $deadline ]; do
        if echo "2003" | sudo -S ip netns exec ue1 ip -4 addr show tun_srsue 2>/dev/null | grep -q "inet"; then
            return 0
        fi
        sleep 2
    done
    return 1
}

get_metric() {
    # get_metric "SELECT mean(avg_sinr) FROM mac_crc_stats WHERE time > now()-90s"
    curl -s -G "${INFLUX}" --data-urlencode "q=$1" 2>/dev/null \
      | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    v = d['results'][0]['series'][0]['values'][0][1]
    print(round(float(v), 2) if v is not None else 'N/A')
except:
    print('N/A')
"
}

run_test() {
    local intf_type="$1"
    local sir="$2"
    local label="${intf_type}_SIR${sir}dB"

    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "TEST: type=${intf_type}  SIR=${sir} dB  (watch Grafana now)"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Stop previous run
    bash "$HOME/Desktop/stop_mac_telemetry.sh" > /dev/null 2>&1
    sleep 3

    # Launch pipeline (no watchdog so crashes are genuine, Grafana stays up)
    bash "$HOME/Desktop/launch_mac_telemetry.sh" \
        --grc --fading \
        --snr "$BASE_SNR" --k-factor "$BASE_K" \
        --interference-type "$intf_type" --sir "$sir" \
        --no-watchdog \
        > /tmp/sweep_launch.log 2>&1

    # Wait for UE to attach
    log "  Waiting ${SETTLE}s for UE to stabilise..."
    if ! wait_for_ue; then
        log "  RESULT: ATTACH_FAILED — UE never attached"
        echo "| ${label} | ATTACH_FAILED | N/A | N/A | N/A |" | tee -a "$OUTPUT"
        return
    fi
    sleep "$SETTLE"

    # Run measurement window
    log "  Measuring for ${DURATION}s..."
    local t_end=$((SECONDS + DURATION))
    local drops=0
    while [ $SECONDS -lt $t_end ]; do
        if ! ue_alive; then
            drops=$((drops + 1))
            log "  UE drop detected at t=$(( DURATION - (t_end - SECONDS) ))s"
            break
        fi
        sleep 5
    done

    # Collect InfluxDB metrics from the measurement window
    local window="${DURATION}s"
    local avg_sinr
    avg_sinr=$(get_metric "SELECT mean(avg_sinr) FROM mac_crc_stats WHERE time > now()-${window}")
    local total_harq
    total_harq=$(get_metric "SELECT sum(harq_failure) FROM mac_crc_stats WHERE time > now()-${window}")
    local avg_bsr
    avg_bsr=$(get_metric "SELECT mean(avg_bytes_per_report) FROM mac_bsr_stats WHERE time > now()-${window}")

    local status
    if [ "$drops" -gt 0 ]; then
        status="CRASHED"
    else
        status="SURVIVED"
    fi

    log "  RESULT: ${status} | avg_sinr=${avg_sinr} dB | harq_failures=${total_harq} | avg_bsr=${avg_bsr} bytes"
    printf "| %-28s | %-10s | %-12s | %-15s | %-12s |\n" \
        "$label" "$status" "${avg_sinr} dB" "${total_harq}" "${avg_bsr} B" \
        | tee -a "$OUTPUT"
}

# ── Test matrix ──────────────────────────────────────────────────────────────
# SIR levels: from weak interference (30 dB) to strong (0 dB)
SIR_LEVELS=(30 25 20 15 10 5 0)
INTF_TYPES=(cw narrowband)

# ── Header ───────────────────────────────────────────────────────────────────
> "$OUTPUT"
hdr "Interference Sweep — $(date)"
log "Base config: SNR=${BASE_SNR} dB, K=${BASE_K} dB, flat Rician"
log "Test duration: ${DURATION}s per test, settle: ${SETTLE}s"
log "Total tests: $((${#SIR_LEVELS[@]} * ${#INTF_TYPES[@]}))"
echo "" | tee -a "$OUTPUT"
printf "| %-28s | %-10s | %-12s | %-15s | %-12s |\n" \
    "Test" "Status" "Avg SINR" "HARQ Failures" "Avg BSR" | tee -a "$OUTPUT"
printf "| %-28s | %-10s | %-12s | %-15s | %-12s |\n" \
    "----------------------------" "----------" "------------" "---------------" "------------" | tee -a "$OUTPUT"

# ── Run tests ─────────────────────────────────────────────────────────────────
for intf in "${INTF_TYPES[@]}"; do
    hdr "Testing interference type: ${intf}"
    for sir in "${SIR_LEVELS[@]}"; do
        run_test "$intf" "$sir"
    done
done

# ── Final cleanup ─────────────────────────────────────────────────────────────
hdr "Sweep complete"
log "Full results saved to: $OUTPUT"
bash "$HOME/Desktop/stop_mac_telemetry.sh" > /dev/null 2>&1

echo ""
echo "════════════════════════════════════════════"
echo "  SUMMARY TABLE"
echo "════════════════════════════════════════════"
grep "^|" "$OUTPUT"
