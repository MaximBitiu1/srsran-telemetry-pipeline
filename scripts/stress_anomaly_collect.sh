#!/usr/bin/env bash
# =============================================================================
#  Stress Anomaly Dataset Collection Script
#
#  Produces labeled anomalous MAC telemetry by applying system-level stressors
#  to a running srsRAN gNB pipeline. Designed to generate data that is visibly
#  different from the baseline without crashing the channel.
#
#  Key design notes (from gNB inspection):
#    - 5 slot-processing threads run at SCHED_FIFO:96 — highest RT priority
#    - gNB RSS ≈ 2.56 GB — cgroup limits must be based on actual RSS
#    - Affinity: all 16 cores — stressors pinned to cores 0-7 (first half)
#    - cpulimit uses multicores units (100 = 1 core, 800 = 8 cores)
#
#  Stressor categories:
#    baseline — no stressor (reference data)
#    cpu      — stress-ng pinned to gNB cores / cpulimit throttle / RT preempt
#    memory   — cgroups v2 limit set as % of actual gNB RSS
#    sched    — demote gNB SCHED_FIFO:96 threads / SCHED_FIFO:97 competitor
#    traffic  — UDP flood / burst / tc netem delay+loss on UE uplink
#    combined — two stressors simultaneously
#
#  Usage:
#    ./stress_anomaly_collect.sh                     # all 23 scenarios
#    ./stress_anomaly_collect.sh --duration 60       # 1 min each (smoke test)
#    ./stress_anomaly_collect.sh --category cpu      # one category
#    ./stress_anomaly_collect.sh --scenarios 0,1,7   # specific IDs
#    ./stress_anomaly_collect.sh --dry-run
# =============================================================================
set -uo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
DURATION=180           # seconds of telemetry collection per scenario
SETTLE_TIME=30         # seconds after launch before stressor activates
STRESSOR_RAMP=5        # seconds after stressor starts before collecting
COOLDOWN=20            # seconds between scenarios
DATASET_DIR="$HOME/Desktop/dataset/stress_$(date +%Y%m%d_%H%M%S)"
LAUNCH_SCRIPT="$HOME/Desktop/launch_mac_telemetry.sh"
STOP_SCRIPT="$HOME/Desktop/stop_mac_telemetry.sh"
DECODER_LOG="/tmp/decoder.log"
SUDO_PASS="2003"
DRY_RUN=false
SELECTED_CATEGORY=""
SELECTED_SCENARIOS=""

# ── Channel selection (Option C) ──────────────────────────────────────────────
# baseline/cpu/memory/sched → clean channel (anomaly is unambiguously from stressor)
# traffic/combined          → fading K=3 SNR=25 (realistic uplink load)
CHANNEL_CLEAN="--no-broker --no-grafana"
CHANNEL_FADING="--fading --k-factor 3 --snr 25 --no-grafana"
BASELINE_FLAGS=""   # if non-empty, overrides per-category selection

# ── gNB CPU cores to target ───────────────────────────────────────────────────
# gNB uses all 16 cores; we pin stressors to first 8 to force competition
GNB_STRESS_CORES="0-7"

# ── iperf3 stress port (separate from baseline on 5201) ──────────────────────
STRESS_IPERF_PORT=5210

# ── Per-scenario measurement ports (separate from stress and baseline) ────────
MEAS_UL_PORT=5213    # 10s UL probe (UE → core, JSON)
MEAS_DL_PORT=5214    # 10s DL probe (core → UE, reverse JSON)

# ── Stressor state ────────────────────────────────────────────────────────────
STRESSOR_PIDS=()
GNB_SCHED_ORIG_FILE="/tmp/gnb_sched_orig.txt"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; NC='\033[0m'
info()     { echo -e "${CYAN}[STRESS]${NC}  $*"; }
ok()       { echo -e "${GREEN}[  OK  ]${NC}  $*"; }
warn()     { echo -e "${YELLOW}[ WARN ]${NC}  $*"; }
fail_msg() { echo -e "${RED}[ FAIL ]${NC}  $*"; }
banner()   { echo -e "${BOLD}${CYAN}$*${NC}"; }
sudoc()    { echo "$SUDO_PASS" | sudo -S "$@" 2>/dev/null; }

# ── Helpers ───────────────────────────────────────────────────────────────────
get_gnb_pid() {
    pgrep -x gnb 2>/dev/null | head -1 || pgrep -f "srsgnb\|gnb" 2>/dev/null | head -1 || true
}

get_gnb_rss_kb() {
    local pid="$1"
    ps -o rss= -p "$pid" 2>/dev/null | tr -d ' ' || echo "2621440"  # fallback 2.5GB
}

# ── Parse flags ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --duration)     DURATION="$2";           shift ;;
        --duration=*)   DURATION="${1#*=}" ;;
        --settle)       SETTLE_TIME="$2";        shift ;;
        --cooldown)     COOLDOWN="$2";           shift ;;
        --category)     SELECTED_CATEGORY="$2";  shift ;;
        --category=*)   SELECTED_CATEGORY="${1#*=}" ;;
        --scenarios)    SELECTED_SCENARIOS="$2"; shift ;;
        --scenarios=*)  SELECTED_SCENARIOS="${1#*=}" ;;
        --baseline)     BASELINE_FLAGS="$2";     shift ;;
        --dry-run)      DRY_RUN=true ;;
        --output)       DATASET_DIR="$2";        shift ;;
        -h|--help)
            cat <<EOF
Usage: $0 [OPTIONS]

Options:
  --duration N      Seconds of telemetry per scenario (default: $DURATION)
  --settle N        Settle time before stressor activates (default: $SETTLE_TIME)
  --cooldown N      Cooldown between scenarios (default: $COOLDOWN)
  --category CAT    Only run: baseline, cpu, memory, sched, traffic, combined
  --scenarios N,M   Comma-separated scenario IDs to run
  --baseline FLAGS  Override per-category channel selection
  --dry-run         Show plan without executing
  --output DIR      Dataset output directory
EOF
            exit 0 ;;
        *) warn "Unknown flag: $1" ;;
    esac
    shift
done

# ── Scenario Definitions ──────────────────────────────────────────────────────
# Format: "ID|LABEL|CATEGORY|STRESSOR_TYPE|STRESSOR_ARGS|DESCRIPTION"
SCENARIOS=(
    # ── Baseline ──
    "00|baseline_clean|baseline|none|none|Perfect baseline: no stressor, clean channel"

    # ── CPU Contention ──
    # Workers pinned to cores 0-7 (same cores gNB RT threads run on)
    "01|cpu_pinned_50pct|cpu|cpu|--workers 4 --load 50 --pin-cores|4 workers @ 50% pinned to gNB cores"
    "02|cpu_pinned_80pct|cpu|cpu|--workers 8 --load 80 --pin-cores|8 workers @ 80% pinned to gNB cores (heavy)"
    "03|cpu_pinned_95pct|cpu|cpu|--workers 8 --load 95 --pin-cores|8 workers @ 95% pinned to gNB cores (extreme)"
    # cpulimit directly throttles gNB (100 = 1 core; gNB normally uses ~800%)
    "04|cpu_cpulimit_600|cpu|cpu|--cpulimit 600|cpulimit gNB to 600% (6 cores max)"
    "05|cpu_cpulimit_300|cpu|cpu|--cpulimit 300|cpulimit gNB to 300% — forces slot timing violations"
    # RT preemption: SCHED_FIFO:97 beats gNB's SCHED_FIFO:96 slot threads
    "06|cpu_rt_preempt|cpu|cpu|--rt-preempt --workers 4|SCHED_FIFO:97 workers preempt gNB slot threads"

    # ── Memory Pressure ──
    # Limits based on actual gNB RSS (~2.56 GB) measured at runtime
    "07|mem_80pct_rss|memory|memory|--dynamic-pct 80|cgroup = 80% of gNB RSS (~2 GB, mild reclaim)"
    "08|mem_60pct_rss|memory|memory|--dynamic-pct 60|cgroup = 60% of gNB RSS (~1.5 GB, moderate reclaim)"
    "09|mem_40pct_rss|memory|memory|--dynamic-pct 40|cgroup = 40% of gNB RSS (~1 GB, heavy reclaim)"
    "10|mem_40pct_balloon|memory|memory|--dynamic-pct 40 --balloon 2G|40% RSS limit + 2 GB balloon"

    # ── Scheduling Starvation ──
    # Target the 5 SCHED_FIFO:96 slot-processing threads directly
    "11|sched_rt_competitor_97|sched|sched|--rt-competitor --rt-prio 97|SCHED_FIFO:97 workers — preempts gNB FIFO:96 slots"
    "12|sched_demote_rt_batch|sched|sched|--demote-gnb-rt batch|Demote 5 slot threads FIFO:96 → SCHED_BATCH"
    "13|sched_demote_rt_other|sched|sched|--demote-gnb-rt other --nice 19|Demote slot threads FIFO:96 → SCHED_OTHER + nice=19"
    "14|sched_demote_rt_plus_cpu|sched|sched|--demote-gnb-rt batch --rt-competitor --rt-prio 70|Demote RT + FIFO:70 competitor"

    # ── Traffic Anomalies ──
    "15|traffic_flood_100m|traffic|traffic|--flood --rate 100M|100 Mbps UDP flood (10× baseline)"
    "16|traffic_flood_150m|traffic|traffic|--flood --rate 150M|150 Mbps UDP flood (15× baseline, extreme)"
    "17|traffic_netem_delay|traffic|traffic|--netem --delay 50ms --jitter 20ms --loss 1|tc netem: 50ms delay, 20ms jitter, 1% loss"
    "18|traffic_burst_aggressive|traffic|traffic|--burst --on 3 --off 1 --rate 120M|Aggressive burst: 3s on/1s off @ 120 Mbps"
    "19|traffic_netem_burst|traffic|traffic|--netem --delay 30ms --jitter 10ms --loss 2 --burst --rate 80M|netem 30ms jitter + burst traffic"

    # ── Combined ──
    "20|combined_rt_preempt_traffic|combined|combined|--rt-preempt --workers 4 --traffic-flood --traffic-rate 80M|RT preemption + 80M flood"
    "21|combined_cpulimit_mem|combined|combined|--cpulimit 300 --mem-pct 60|cpulimit 300% + memory 60% RSS"
    "22|combined_demote_traffic|combined|combined|--demote-gnb-rt batch --traffic-flood --traffic-rate 100M|Demote RT threads + 100M flood"
)

# ── Filtering ─────────────────────────────────────────────────────────────────
is_selected() {
    local id="$1" category="$2"
    if [[ -n "$SELECTED_CATEGORY" ]] && [[ "$category" != "$SELECTED_CATEGORY" ]]; then
        return 1
    fi
    if [[ -z "$SELECTED_SCENARIOS" ]]; then return 0; fi
    local num="${id#0}"
    echo ",$SELECTED_SCENARIOS," | grep -q ",$num," && return 0
    echo ",$SELECTED_SCENARIOS," | grep -q ",$id,"  && return 0
    return 1
}

# ── Per-category channel selection ────────────────────────────────────────────
get_channel_flags() {
    local category="$1" stressor_args="$2"
    if [[ -n "$BASELINE_FLAGS" ]]; then echo "$BASELINE_FLAGS"; return; fi
    case "$category" in
        baseline|cpu|memory|sched) echo "$CHANNEL_CLEAN" ;;
        traffic) echo "$CHANNEL_FADING" ;;
        combined)
            if echo "$stressor_args" | grep -q "traffic"; then
                echo "$CHANNEL_FADING"
            else
                echo "$CHANNEL_CLEAN"
            fi ;;
        *) echo "$CHANNEL_CLEAN" ;;
    esac
}

# ── Dependency Check ──────────────────────────────────────────────────────────
check_deps() {
    local missing=()
    command -v stress-ng  &>/dev/null || missing+=("stress-ng")
    command -v cpulimit   &>/dev/null || missing+=("cpulimit")
    command -v chrt       &>/dev/null || missing+=("chrt")
    command -v iperf3     &>/dev/null || missing+=("iperf3")
    command -v taskset    &>/dev/null || missing+=("taskset")
    if ! grep -q "cgroup2" /proc/mounts 2>/dev/null; then
        missing+=("cgroups-v2")
    fi
    if [[ ${#missing[@]} -gt 0 ]]; then
        warn "Missing: ${missing[*]}"
        warn "Install: sudo apt-get install stress-ng cpulimit util-linux iperf3"
        if [[ "${missing[*]}" == *"stress-ng"* || "${missing[*]}" == *"cpulimit"* ]] && ! $DRY_RUN; then
            fail_msg "stress-ng and cpulimit required — aborting"; exit 1
        fi
    else
        ok "All dependencies present"
    fi
}

# ── Stressor: CPU ─────────────────────────────────────────────────────────────
apply_cpu_stressor() {
    local workers=4 load=80 pin_cores=false cpulimit_pct="" rt_preempt=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --workers)    workers="$2";     shift ;;
            --load)       load="$2";        shift ;;
            --pin-cores)  pin_cores=true ;;
            --cpulimit)   cpulimit_pct="$2"; shift ;;
            --rt-preempt) rt_preempt=true ;;
        esac
        shift
    done

    local gnb_pid; gnb_pid=$(get_gnb_pid)

    if [[ -n "$cpulimit_pct" ]]; then
        # Throttle the gNB process directly — most direct CPU stressor
        if [[ -z "$gnb_pid" ]]; then
            warn "gNB not found — cannot apply cpulimit"; return 1
        fi
        info "cpulimit: throttling gNB PID $gnb_pid to ${cpulimit_pct}% CPU"
        sudoc cpulimit -p "$gnb_pid" -l "$cpulimit_pct" -b 2>/dev/null
        # cpulimit daemonizes with -b so track by pid lookup
        sleep 1
        local cl_pid; cl_pid=$(pgrep -f "cpulimit.*$gnb_pid" | head -1 || true)
        [[ -n "$cl_pid" ]] && STRESSOR_PIDS+=($cl_pid) && ok "cpulimit PID $cl_pid (gNB → ${cpulimit_pct}% max)"
        return
    fi

    if $rt_preempt; then
        # SCHED_FIFO:97 workers — preempt gNB's SCHED_FIFO:96 slot threads
        info "RT preemption: $workers SCHED_FIFO:97 workers on cores $GNB_STRESS_CORES"
        sudoc taskset -c "$GNB_STRESS_CORES" \
            chrt -f 97 \
            stress-ng --cpu "$workers" --cpu-load 90 --timeout 0 \
            >/tmp/stress_cpu_rt.log 2>&1 &
        STRESSOR_PIDS+=($!)
        ok "RT preempt workers PID ${STRESSOR_PIDS[-1]}"
        return
    fi

    local taskset_prefix=""
    if $pin_cores; then
        taskset_prefix="taskset -c $GNB_STRESS_CORES"
        info "CPU stressor: $workers workers @ $load% pinned to cores $GNB_STRESS_CORES"
    else
        info "CPU stressor: $workers workers @ $load%"
    fi

    # shellcheck disable=SC2086
    $taskset_prefix stress-ng --cpu "$workers" --cpu-load "$load" \
        --metrics-brief --timeout 0 >/tmp/stress_cpu.log 2>&1 &
    STRESSOR_PIDS+=($!)
    ok "CPU stressor PID ${STRESSOR_PIDS[-1]}"
}

# ── Stressor: Memory ──────────────────────────────────────────────────────────
CGROUP_NAME="srsran_stress_test"
CGROUP_PATH="/sys/fs/cgroup/$CGROUP_NAME"

apply_mem_stressor() {
    local dynamic_pct="" balloon=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dynamic-pct) dynamic_pct="$2"; shift ;;
            --balloon)     balloon="$2";     shift ;;
        esac
        shift
    done

    local gnb_pid; gnb_pid=$(get_gnb_pid)
    if [[ -z "$gnb_pid" ]]; then
        warn "gNB not found — skipping memory stressor"; return 1
    fi

    # Compute limit based on actual gNB RSS
    local rss_kb; rss_kb=$(get_gnb_rss_kb "$gnb_pid")
    local limit_kb=$(( rss_kb * dynamic_pct / 100 ))
    local limit_bytes=$(( limit_kb * 1024 ))
    local limit_mb=$(( limit_kb / 1024 ))

    info "Memory stressor: gNB RSS=${rss_kb}KB → limit=${dynamic_pct}% = ${limit_mb}MB"

    sudoc mkdir -p "$CGROUP_PATH"
    echo "$limit_bytes" | sudoc tee "$CGROUP_PATH/memory.high" >/dev/null
    echo "$gnb_pid"     | sudoc tee "$CGROUP_PATH/cgroup.procs" >/dev/null
    ok "gNB PID $gnb_pid → cgroup (memory.high=${limit_mb}MB)"

    if [[ -n "$balloon" ]]; then
        info "Memory balloon: stress-ng --vm 1 --vm-bytes $balloon"
        stress-ng --vm 1 --vm-bytes "$balloon" --vm-keep --timeout 0 \
            >/tmp/stress_mem.log 2>&1 &
        STRESSOR_PIDS+=($!)
        ok "Balloon PID ${STRESSOR_PIDS[-1]}"
    fi
}

# ── Stressor: Scheduling ──────────────────────────────────────────────────────
apply_sched_stressor() {
    local rt_competitor=false rt_prio=70 demote_target="" nice_val=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --rt-competitor) rt_competitor=true ;;
            --rt-prio)       rt_prio="$2"; shift ;;
            --demote-gnb-rt) demote_target="$2"; shift ;;
            --nice)          nice_val="$2"; shift ;;
        esac
        shift
    done

    local gnb_pid; gnb_pid=$(get_gnb_pid)
    if [[ -z "$gnb_pid" ]]; then
        warn "gNB not found — skipping sched stressor"; return 1
    fi

    # Save original scheduler state for ALL gNB threads before modifying
    echo "" > "$GNB_SCHED_ORIG_FILE"
    for tid in $(ls /proc/"$gnb_pid"/task/ 2>/dev/null); do
        local policy prio
        policy=$(sudoc chrt -p "$tid" 2>/dev/null | grep -oP 'policy: \K\S+' || echo "SCHED_OTHER")
        prio=$(sudoc   chrt -p "$tid" 2>/dev/null | grep -oP 'priority: \K\d+'  || echo "0")
        echo "$tid $policy $prio" >> "$GNB_SCHED_ORIG_FILE"
    done

    # Demote gNB's SCHED_FIFO:96 slot threads
    if [[ -n "$demote_target" ]]; then
        local demoted=0
        while IFS=' ' read -r tid policy prio; do
            [[ -z "$tid" ]] && continue
            if [[ "$policy" == "SCHED_FIFO" && "$prio" -ge 50 ]]; then
                case "$demote_target" in
                    batch) sudoc chrt -b -p 0 "$tid" >/dev/null 2>&1 && demoted=$((demoted+1)) ;;
                    other) sudoc chrt -o -p 0 "$tid" >/dev/null 2>&1 && demoted=$((demoted+1)) ;;
                esac
                [[ -n "$nice_val" ]] && sudoc renice "$nice_val" -p "$tid" >/dev/null 2>&1 || true
            fi
        done < "$GNB_SCHED_ORIG_FILE"
        ok "Demoted $demoted gNB RT threads (FIFO:96 → SCHED_${demote_target^^})"
    fi

    # RT competitor: SCHED_FIFO at given priority — preempts any gNB thread below this
    if $rt_competitor; then
        info "RT competitor: SCHED_FIFO:$rt_prio workers on cores $GNB_STRESS_CORES"
        sudoc taskset -c "$GNB_STRESS_CORES" \
            chrt -f "$rt_prio" \
            stress-ng --cpu 2 --cpu-load 85 --timeout 0 \
            >/tmp/stress_rt.log 2>&1 &
        STRESSOR_PIDS+=($!)
        ok "RT competitor PID ${STRESSOR_PIDS[-1]} (FIFO:$rt_prio)"
    fi
}

# ── Stressor: Traffic ─────────────────────────────────────────────────────────
apply_traffic_stressor() {
    local mode="flood" rate="100M" pkt_size=1400
    local on_time=5 off_time=5
    local netem=false netem_delay="50ms" netem_jitter="20ms" netem_loss="1"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --flood)    mode="flood" ;;
            --burst)    mode="burst" ;;
            --rate)     rate="$2";        shift ;;
            --pkt-size) pkt_size="$2";    shift ;;
            --on)       on_time="$2";     shift ;;
            --off)      off_time="$2";    shift ;;
            --netem)    netem=true ;;
            --delay)    netem_delay="$2"; shift ;;
            --jitter)   netem_jitter="$2"; shift ;;
            --loss)     netem_loss="$2";  shift ;;
        esac
        shift
    done

    local ue_ip
    ue_ip=$(sudoc ip netns exec ue1 ip -4 addr show tun_srsue 2>/dev/null \
            | grep -oP 'inet \K[\d.]+' || true)
    if [[ -z "$ue_ip" ]]; then
        warn "UE TUN not found — skipping traffic stressor"; return 1
    fi

    # Apply tc netem on UE uplink (adds delay/jitter/loss to user-plane traffic)
    if $netem; then
        info "tc netem on tun_srsue: delay=$netem_delay jitter=$netem_jitter loss=${netem_loss}%"
        sudoc ip netns exec ue1 \
            tc qdisc add dev tun_srsue root netem \
            delay "$netem_delay" jitter "$netem_jitter" loss "${netem_loss}%" 2>/dev/null || true
        ok "tc netem applied"
    fi

    # Only inject iperf3 stress if mode is specified
    if [[ "$mode" != "netem_only" ]]; then
        local target="10.45.0.1"
        iperf3 -s -p "$STRESS_IPERF_PORT" -D 2>/dev/null || true
        sleep 1

        case "$mode" in
            flood)
                info "UDP flood: $rate pkt=${pkt_size}B → $target:$STRESS_IPERF_PORT"
                sudoc ip netns exec ue1 iperf3 -c "$target" -p "$STRESS_IPERF_PORT" \
                    -u -b "$rate" -t 9999 -l "$pkt_size" \
                    >/tmp/stress_traffic.log 2>&1 &
                STRESSOR_PIDS+=($!)
                ok "UDP flood PID ${STRESSOR_PIDS[-1]}"
                ;;
            burst)
                info "Burst traffic: ${on_time}s on / ${off_time}s off @ $rate"
                (
                    trap 'exit 0' TERM INT
                    while true; do
                        sudoc ip netns exec ue1 iperf3 -c "$target" -p "$STRESS_IPERF_PORT" \
                            -u -b "$rate" -t "$on_time" -l "$pkt_size" \
                            >/tmp/stress_traffic.log 2>&1 || true
                        sleep "$off_time"
                    done
                ) &
                STRESSOR_PIDS+=($!)
                ok "Burst traffic PID ${STRESSOR_PIDS[-1]}"
                ;;
        esac
    fi
}

# ── Stressor: Combined ────────────────────────────────────────────────────────
apply_combined_stressor() {
    local rt_preempt=false workers=4 cpulimit_pct="" mem_pct=""
    local demote_target="" traffic_mode="" traffic_rate="80M"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --rt-preempt)   rt_preempt=true ;;
            --workers)      workers="$2";      shift ;;
            --cpulimit)     cpulimit_pct="$2"; shift ;;
            --mem-pct)      mem_pct="$2";      shift ;;
            --demote-gnb-rt) demote_target="$2"; shift ;;
            --traffic-flood) traffic_mode="flood" ;;
            --traffic-burst) traffic_mode="burst" ;;
            --traffic-rate)  traffic_rate="$2"; shift ;;
        esac
        shift
    done

    if $rt_preempt; then
        apply_cpu_stressor --rt-preempt --workers "$workers"
    fi
    if [[ -n "$cpulimit_pct" ]]; then
        apply_cpu_stressor --cpulimit "$cpulimit_pct"
    fi
    if [[ -n "$mem_pct" ]]; then
        apply_mem_stressor --dynamic-pct "$mem_pct"
    fi
    if [[ -n "$demote_target" ]]; then
        apply_sched_stressor --demote-gnb-rt "$demote_target"
    fi
    if [[ -n "$traffic_mode" ]]; then
        apply_traffic_stressor "--$traffic_mode" --rate "$traffic_rate"
    fi
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
apply_stressor() {
    local stressor_type="$1"; shift
    STRESSOR_PIDS=()
    if [[ "$stressor_type" == "none" ]]; then
        info "No stressor — baseline collection"; return
    fi
    case "$stressor_type" in
        cpu)      apply_cpu_stressor      "$@" ;;
        memory)   apply_mem_stressor      "$@" ;;
        sched)    apply_sched_stressor    "$@" ;;
        traffic)  apply_traffic_stressor  "$@" ;;
        combined) apply_combined_stressor "$@" ;;
        *) warn "Unknown stressor: $stressor_type" ;;
    esac
}

# ── Stressor Cleanup ──────────────────────────────────────────────────────────
remove_stressor() {
    local stressor_type="$1"
    info "Removing stressor ($stressor_type)..."

    # Kill tracked PIDs
    for pid in "${STRESSOR_PIDS[@]:-}"; do
        [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
    done

    # Sweeps
    pkill -f "stress-ng"                         2>/dev/null || true
    pkill -f "cpulimit"                          2>/dev/null || true
    pkill -f "iperf3.*-p $STRESS_IPERF_PORT"     2>/dev/null || true
    pkill -f "iperf3 -s -p $STRESS_IPERF_PORT"  2>/dev/null || true

    # Restore gNB scheduler (sched stressors)
    if [[ -f "$GNB_SCHED_ORIG_FILE" ]]; then
        local restored=0
        while IFS=' ' read -r tid policy prio; do
            [[ -z "$tid" ]] && continue
            case "$policy" in
                SCHED_FIFO) sudoc chrt -f -p "$prio" "$tid" >/dev/null 2>&1 && restored=$((restored+1)) || true ;;
                SCHED_RR)   sudoc chrt -r -p "$prio" "$tid" >/dev/null 2>&1 && restored=$((restored+1)) || true ;;
            esac
        done < "$GNB_SCHED_ORIG_FILE"
        [[ $restored -gt 0 ]] && ok "Restored $restored gNB thread schedulers"
        rm -f "$GNB_SCHED_ORIG_FILE"
    fi

    # Remove tc netem from UE namespace
    if [[ "$stressor_type" == "traffic" || "$stressor_type" == "combined" ]]; then
        sudoc ip netns exec ue1 tc qdisc del dev tun_srsue root 2>/dev/null || true
        ok "tc netem removed"
    fi

    # Tear down cgroup
    if [[ "$stressor_type" == "memory" || "$stressor_type" == "combined" ]]; then
        if [[ -d "$CGROUP_PATH" ]]; then
            local gnb_pid; gnb_pid=$(get_gnb_pid)
            [[ -n "$gnb_pid" ]] && echo "$gnb_pid" | sudoc tee /sys/fs/cgroup/cgroup.procs >/dev/null 2>&1 || true
            echo "max" | sudoc tee "$CGROUP_PATH/memory.high" >/dev/null 2>&1 || true
            sleep 1
            sudoc rmdir "$CGROUP_PATH" 2>/dev/null || true
            ok "cgroup $CGROUP_NAME removed"
        fi
    fi

    STRESSOR_PIDS=()
    ok "Stressor cleaned up"
}

# ── Per-Scenario Latency/Throughput Measurement ───────────────────────────────
# Run a 10s iperf3 UL+DL probe and extract ping RTT stats WHILE stressor is active.
# Args: $1 = output directory
# Stdout (last line): "ul_mbps dl_mbps rtt_avg_ms rtt_max_ms"
measure_scenario() {
    local meas_dir="$1"
    mkdir -p "$meas_dir"

    local ue_ip
    ue_ip=$(sudoc ip netns exec ue1 ip -4 addr show tun_srsue 2>/dev/null \
            | grep -oP 'inet \K[\d.]+' || true)

    if [[ -z "$ue_ip" ]]; then
        warn "UE TUN not found — skipping latency/throughput measurement"
        printf "ul_mbps=N/A\ndl_mbps=N/A\nrtt_avg_ms=N/A\nrtt_max_ms=N/A\n" \
            > "$meas_dir/summary.txt"
        echo "N/A N/A N/A N/A"
        return 1
    fi

    # UL probe: UE → core (10s, UDP 10M)
    info "  Probe UL (10s @ 10M UDP)..."
    iperf3 -s -B 10.45.0.1 -p "$MEAS_UL_PORT" -D 2>/dev/null || true
    sleep 0.5
    sudoc ip netns exec ue1 iperf3 -c 10.45.0.1 -p "$MEAS_UL_PORT" \
        -u -b 10M -t 10 -l 1400 -J \
        > "$meas_dir/iperf_ul.json" 2>&1 || true
    pkill -f "iperf3.*-p $MEAS_UL_PORT" 2>/dev/null || true

    # DL probe: core → UE (10s, UDP 5M, reverse)
    info "  Probe DL (10s @ 5M UDP reverse)..."
    iperf3 -s -B 10.45.0.1 -p "$MEAS_DL_PORT" -D 2>/dev/null || true
    sleep 0.5
    sudoc ip netns exec ue1 iperf3 -c 10.45.0.1 -p "$MEAS_DL_PORT" \
        -u -b 5M -t 10 -l 1400 -J --reverse \
        > "$meas_dir/iperf_dl.json" 2>&1 || true
    pkill -f "iperf3.*-p $MEAS_DL_PORT" 2>/dev/null || true

    # Parse throughput from JSON (bits_per_second → Mbps)
    local ul_mbps dl_mbps
    ul_mbps=$(python3 -c "
import json
try:
    d = json.load(open('$meas_dir/iperf_ul.json'))
    print(f\"{d['end']['sum']['bits_per_second']/1e6:.2f}\")
except Exception as e:
    print('N/A')
" 2>/dev/null || echo "N/A")

    dl_mbps=$(python3 -c "
import json
try:
    d = json.load(open('$meas_dir/iperf_dl.json'))
    print(f\"{d['end']['sum']['bits_per_second']/1e6:.2f}\")
except Exception as e:
    print('N/A')
" 2>/dev/null || echo "N/A")

    # Extract ping RTT from the last 30 samples in the running ping log
    local rtt_avg="N/A" rtt_max="N/A"
    if [[ -f /tmp/ping_ue.log ]]; then
        rtt_avg=$(grep -oP 'time=\K[\d.]+' /tmp/ping_ue.log | tail -30 | \
            awk 'NR>0{s+=$1; n++} END {if(n>0) printf "%.3f", s/n; else print "N/A"}' \
            2>/dev/null || echo "N/A")
        rtt_max=$(grep -oP 'time=\K[\d.]+' /tmp/ping_ue.log | tail -30 | \
            awk 'BEGIN{max=0} {if($1+0>max+0) max=$1} END {if(NR>0) printf "%.3f", max; else print "N/A"}' \
            2>/dev/null || echo "N/A")
    fi

    # Write summary
    printf "ul_mbps=%s\ndl_mbps=%s\nrtt_avg_ms=%s\nrtt_max_ms=%s\n" \
        "$ul_mbps" "$dl_mbps" "$rtt_avg" "$rtt_max" \
        | tee "$meas_dir/summary.txt" >/dev/null

    ok "  Measurement: UL=${ul_mbps}Mbps DL=${dl_mbps}Mbps RTT avg=${rtt_avg}ms max=${rtt_max}ms"
    echo "$ul_mbps $dl_mbps $rtt_avg $rtt_max"
}

# ── Run a Single Scenario ─────────────────────────────────────────────────────
run_scenario() {
    local id="$1" label="$2" category="$3" stressor_type="$4"
    local stressor_args="$5" description="$6"
    local logfile="$DATASET_DIR/$category/${id}_${label}.log"
    mkdir -p "$DATASET_DIR/$category"

    banner "═══════════════════════════════════════════════════════"
    banner "  Scenario $id: $label"
    banner "  Category: $category | Stressor: $stressor_type"
    banner "  $description"
    banner "═══════════════════════════════════════════════════════"

    local channel_flags
    channel_flags=$(get_channel_flags "$category" "$stressor_args")

    if $DRY_RUN; then
        info "[DRY RUN] Channel: $channel_flags"
        info "[DRY RUN] Stressor: $stressor_type $stressor_args"
        info "[DRY RUN] Output: $logfile"
        echo "$id,$label,$category,$stressor_type,\"$stressor_args\",\"$description\",dry_run,0,0,$logfile,N/A,N/A,N/A,N/A" \
            >> "$DATASET_DIR/manifest.csv"
        return 0
    fi

    > "$DECODER_LOG" 2>/dev/null || true

    # ── Phase 1: Launch pipeline ──
    info "Launching pipeline ($channel_flags)..."
    # shellcheck disable=SC2086
    bash "$LAUNCH_SCRIPT" $channel_flags >/tmp/stress_launch.log 2>&1 || true
    tail -5 /tmp/stress_launch.log

    if ! get_gnb_pid &>/dev/null; then
        fail_msg "Pipeline failed to start — skipping scenario $id"
        echo "$id,$label,$category,$stressor_type,\"$stressor_args\",\"$description\",launch_failed,0,0,$logfile,N/A,N/A,N/A,N/A" \
            >> "$DATASET_DIR/manifest.csv"
        bash "$STOP_SCRIPT" >/dev/null 2>&1 || true
        sleep "$COOLDOWN"; return 1
    fi

    # ── Phase 2: Settle ──
    info "Settling ${SETTLE_TIME}s (baseline channel, no stressor)..."
    sleep "$SETTLE_TIME"

    if ! pgrep -f "srsue" &>/dev/null; then
        fail_msg "UE died during settle — aborting scenario $id"
        echo "$id,$label,$category,$stressor_type,\"$stressor_args\",\"$description\",ue_died_settle,0,0,$logfile,N/A,N/A,N/A,N/A" \
            >> "$DATASET_DIR/manifest.csv"
        bash "$STOP_SCRIPT" >/dev/null 2>&1 || true
        sleep "$COOLDOWN"; return 1
    fi

    # ── Phase 3: Apply stressor ──
    # shellcheck disable=SC2086
    apply_stressor "$stressor_type" $stressor_args
    info "Stressor ramp ${STRESSOR_RAMP}s..."
    sleep "$STRESSOR_RAMP"

    # ── Phase 4: Collect ──
    local collect_start; collect_start=$(date +%s)
    info "Collecting telemetry for ${DURATION}s..."
    local elapsed=0
    while [[ $elapsed -lt $DURATION ]]; do
        sleep 10
        elapsed=$((elapsed + 10))
        if ! pgrep -f "srsue" &>/dev/null; then
            warn "UE crashed at ${elapsed}s"
            break
        fi
        printf "\r  [%3d%%] %d/%ds" "$((elapsed * 100 / DURATION))" "$elapsed" "$DURATION"
    done
    echo ""

    local collect_end; collect_end=$(date +%s)
    local actual_duration=$((collect_end - collect_start))

    # ── Phase 4.5: Latency/throughput snapshot (under active stressor) ──
    info "Capturing latency/throughput snapshot..."
    local meas_dir="$DATASET_DIR/$category/${id}_${label}_meas"
    local meas_vals
    meas_vals=$(measure_scenario "$meas_dir" 2>/dev/null || echo "N/A N/A N/A N/A")
    local meas_ul meas_dl meas_rtt_avg meas_rtt_max
    read -r meas_ul meas_dl meas_rtt_avg meas_rtt_max <<< "$meas_vals"

    # ── Phase 5: Remove stressor ──
    remove_stressor "$stressor_type"

    local line_count=0
    [[ -f "$DECODER_LOG" ]] && line_count=$(wc -l < "$DECODER_LOG")

    local status="complete"
    if ! pgrep -f "srsue" &>/dev/null; then
        status="ue_crashed"
        warn "UE did not survive scenario $id"
    fi

    if [[ -f "$DECODER_LOG" && $line_count -gt 0 ]]; then
        cp "$DECODER_LOG" "$logfile"
        ok "Saved $line_count lines → $(basename "$logfile")"
    else
        warn "No telemetry data for scenario $id"
        status="no_data"
    fi

    echo "$id,$label,$category,$stressor_type,\"$stressor_args\",\"$description\",$status,$actual_duration,$line_count,$logfile,$meas_ul,$meas_dl,$meas_rtt_avg,$meas_rtt_max" \
        >> "$DATASET_DIR/manifest.csv"

    info "Stopping pipeline..."
    bash "$STOP_SCRIPT" >/dev/null 2>&1 || true
    info "Cooldown ${COOLDOWN}s..."
    sleep "$COOLDOWN"

    ok "Scenario $id done: $status | ${actual_duration}s | $line_count lines"
    return 0
}

# ── Main ──────────────────────────────────────────────────────────────────────
banner ""
banner "╔═══════════════════════════════════════════════════════╗"
banner "║     Stress Anomaly Dataset Collection                 ║"
banner "╚═══════════════════════════════════════════════════════╝"
banner ""

check_deps

mkdir -p "$DATASET_DIR"
info "Output:                   $DATASET_DIR"
info "Duration/scenario:        ${DURATION}s (settle ${SETTLE_TIME}s + ramp ${STRESSOR_RAMP}s)"
if [[ -n "$BASELINE_FLAGS" ]]; then
    info "Channel (override):       $BASELINE_FLAGS"
else
    info "Channel baseline/cpu/mem/sched: $CHANNEL_CLEAN"
    info "Channel traffic/combined:       $CHANNEL_FADING"
fi
[[ -n "$SELECTED_CATEGORY" ]] && info "Category filter: $SELECTED_CATEGORY"

total=0
for S in "${SCENARIOS[@]}"; do
    IFS='|' read -r id label category stressor_type stressor_args description <<< "$S"
    is_selected "$id" "$category" && total=$((total + 1))
done
info "Scenarios to run: $total"
est_min=$(( (total * (SETTLE_TIME + STRESSOR_RAMP + DURATION + COOLDOWN)) / 60 ))
info "Estimated time:   ~${est_min} minutes"
echo ""

echo "id,label,category,stressor_type,stressor_args,description,status,duration_s,lines,logfile,ul_mbps,dl_mbps,rtt_avg_ms,rtt_max_ms" \
    > "$DATASET_DIR/manifest.csv"

completed=0; failed=0
for S in "${SCENARIOS[@]}"; do
    IFS='|' read -r id label category stressor_type stressor_args description <<< "$S"
    is_selected "$id" "$category" || continue

    completed=$((completed + 1))
    info "[$completed/$total] Starting scenario $id..."

    if run_scenario "$id" "$label" "$category" "$stressor_type" "$stressor_args" "$description"; then
        ok "[$completed/$total] $id — PASSED"
    else
        failed=$((failed + 1))
        warn "[$completed/$total] $id — FAILED"
    fi
done

# ── Summary ───────────────────────────────────────────────────────────────────
banner ""
banner "╔═══════════════════════════════════════════════════════╗"
banner "║     Collection Complete                               ║"
banner "╚═══════════════════════════════════════════════════════╝"
banner ""

{
    echo "Stress Anomaly Dataset Collection Summary"
    echo "========================================="
    echo "Date:              $(date)"
    echo "Duration/scenario: ${DURATION}s"
    echo "Total scenarios:   $total"
    echo "Passed:            $((completed - failed))"
    echo "Failed:            $failed"
    echo ""
    echo "Scenario Results:"
    echo "-----------------"
    tail -n +2 "$DATASET_DIR/manifest.csv" | \
    while IFS=, read -r sid slabel scat stype sargs sdesc sstatus sdur slines slog; do
        printf "  %-4s %-35s %-10s %-10s %6ss  %8s lines  [%s]\n" \
            "$sid" "$slabel" "$scat" "$stype" "$sdur" "$slines" "$sstatus"
    done
    echo ""
    echo "Files by category:"
    for cat_dir in "$DATASET_DIR"/*/; do
        cat_name=$(basename "$cat_dir")
        count=$(ls "$cat_dir"*.log 2>/dev/null | wc -l)
        size=$(du -sh "$cat_dir" 2>/dev/null | cut -f1)
        printf "  %-12s %2d logs   %s\n" "$cat_name" "$count" "$size"
    done
    echo ""
    echo "Total dataset size: $(du -sh "$DATASET_DIR" | cut -f1)"
} | tee "$DATASET_DIR/summary.txt"

echo ""
info "Manifest: $DATASET_DIR/manifest.csv"
info "Summary:  $DATASET_DIR/summary.txt"
echo ""
info "To plot a scenario:"
echo "  python3 ~/Desktop/plot_all_telemetry.py \$DATASET_DIR/<scenario>.log"
