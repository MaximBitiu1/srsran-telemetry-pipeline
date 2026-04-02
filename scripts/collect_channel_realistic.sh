#!/usr/bin/env bash
# =============================================================================
#  Realistic Channel Dataset Collection Script
#
#  Collects telemetry under 10 real-world-grounded 5G channel scenarios:
#    - 2 Baselines  (indoor LoS, pedestrian NLoS)
#    - 5 High-probability (vehicular urban, cell edge, highway, PIM, drive-by)
#    - 3 Edge cases  (deep urban canyon, Rayleigh worst-case, high-speed train)
#
#  All scenarios use the GRC broker (--grc) with --no-grafana.
#  Band 3 (1.8 GHz) — Doppler formula: f_d (Hz) = speed (km/h) × 1.667
#
#  Usage:
#    ./collect_channel_realistic.sh                    # run all 10 scenarios
#    ./collect_channel_realistic.sh --duration 120     # 2 min per scenario
#    ./collect_channel_realistic.sh --scenarios B1,R1  # run specific scenarios
#    ./collect_channel_realistic.sh --dry-run          # preview without running
#    ./collect_channel_realistic.sh --output DIR       # custom output dir
#
#  Estimated runtime (defaults):
#    10 scenarios × (180s collect + 30s settle + 15s cooldown) ≈ 37.5 min
#
#  Output:
#    ~/Desktop/datasets/channel/<timestamp>/
#      ├── manifest.csv
#      ├── B1_pedestrian_indoor_office.log
#      ├── ...
#      └── summary.txt
# =============================================================================
set -uo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
DURATION=180
SETTLE_TIME=30
COOLDOWN=15
DATASET_DIR="$HOME/Desktop/channel_dataset/$(date +%Y%m%d_%H%M%S)"
LAUNCH_SCRIPT="$HOME/Desktop/launch_mac_telemetry.sh"
STOP_SCRIPT="$HOME/Desktop/stop_mac_telemetry.sh"
DECODER_LOG="/tmp/decoder.log"
DRY_RUN=false
SELECTED_SCENARIOS=""

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${CYAN}[COLLECT]${NC}  $*"; }
ok()    { echo -e "${GREEN}[  OK   ]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[ WARN  ]${NC}  $*"; }
fail()  { echo -e "${RED}[ FAIL  ]${NC}  $*"; }
banner(){ echo -e "${BOLD}${CYAN}$*${NC}"; }

# ── Parse flags ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration)    DURATION="$2";      shift ;;
    --duration=*)  DURATION="${1#*=}"  ;;
    --settle)      SETTLE_TIME="$2";   shift ;;
    --settle=*)    SETTLE_TIME="${1#*=}" ;;
    --cooldown)    COOLDOWN="$2";      shift ;;
    --cooldown=*)  COOLDOWN="${1#*=}"  ;;
    --scenarios)   SELECTED_SCENARIOS="$2"; shift ;;
    --scenarios=*) SELECTED_SCENARIOS="${1#*=}" ;;
    --dry-run)     DRY_RUN=true ;;
    --output)      DATASET_DIR="$2";   shift ;;
    --output=*)    DATASET_DIR="${1#*=}" ;;
    -h|--help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --duration N      Seconds of telemetry per scenario (default: $DURATION)"
      echo "  --settle N        Settle time after launch (default: $SETTLE_TIME)"
      echo "  --cooldown N      Cooldown between scenarios (default: $COOLDOWN)"
      echo "  --scenarios LIST  Comma-separated IDs to run (e.g. B1,R1,R3,E1)"
      echo "  --dry-run         Preview scenarios without running"
      echo "  --output DIR      Output directory"
      echo "  -h, --help        Show this help"
      echo ""
      echo "Scenario IDs: B1 B2 R1 R2 R3 R4 R5 E1 E2 E3"
      exit 0 ;;
    *) warn "Unknown flag: $1" ;;
  esac
  shift
done

# ── Scenario Definitions ──────────────────────────────────────────────────────
# Format: "ID|LABEL|CATEGORY|LAUNCH_FLAGS|DESCRIPTION"
#
# Real-world context (Band 3, 1.8 GHz):
#   f_d (Hz) = speed (km/h) × 1.667
#   EPA: delay spread 410 ns  → indoor/pedestrian (well inside CP 4687 ns)
#   EVA: delay spread 2510 ns → urban macro       (well inside CP)
#   ETU: delay spread 5000 ns → dense urban canyon (exceeds CP → real ISI)
#   K-factor: 6 = strong LoS,  3 = mixed,  0 = full Rayleigh
#
# Telemetry impact expected per scenario is documented in each description.
SCENARIOS=(
  # ══════════════════════════════════════════════════════════════════════════════
  # BASELINES — steady-state reference points (2 scenarios)
  # Purpose: establish what "normal" looks like across all metrics.
  # Expected: flat SINR, stable MCS≈28, HARQ≈0, BSR steady, RLC delay low.
  # ══════════════════════════════════════════════════════════════════════════════

  # B1: Indoor office, strong LoS (K=6, SNR=25, fd=2 Hz ≈ 1.2 km/h).
  #     Stressed metrics: NONE (this is the clean reference).
  #     All other scenarios are measured relative to this.
  "B1|baseline_indoor_los|baseline|--grc --fading --k-factor 6 --snr 25 --doppler 2|BASELINE: Indoor LoS office. K=6dB, SNR=25dB, fd=2Hz. Flat metrics — all-scenario reference point."

  # B2: Pedestrian NLoS (EPA-5, SNR=22, fd=5 Hz ≈ 3 km/h walking).
  #     Stressed metrics: mild MCS variation, occasional HARQ retx.
  #     3GPP EPA-5 standard pedestrian NLoS reference.
  "B2|baseline_pedestrian_nlos|baseline|--grc --fading --profile epa --snr 22 --doppler 5|BASELINE: Pedestrian NLoS urban street. EPA-5 (3GPP ref), SNR=22dB. Mild ISI, occasional retx."

  # ══════════════════════════════════════════════════════════════════════════════
  # TIME-VARYING SCENARIOS — non-stationary, stresses ALL metrics dynamically (5)
  #
  # Why time-varying is critical:
  #   Steady-state → metrics settle to one operating point after settle period.
  #   Time-varying → SNR drops → MCS drops → HARQ failures burst → RLC delay
  #   spikes → BSR builds → PDCP throughput collapses → then all recover.
  #   That correlated multi-metric transition is the anomaly signal.
  #
  # GRC broker time-varying modes:
  #   drive-by:    30s sinusoidal cycle, SNR swings ±8dB, Doppler 5→200→5 Hz,
  #                drops 0→2%→0. Models bus/truck blocking LoS periodically.
  #   urban-walk:  bounded random walk, SNR base±10dB, Doppler 1-20 Hz,
  #                15% chance of 5% burst-drop each second. Models UE moving
  #                through urban multipath environment.
  #   edge-of-cell: 60s linear decline, SNR base→12dB, drops 0→10%.
  #                Models UE moving away from cell toward coverage boundary.
  # ══════════════════════════════════════════════════════════════════════════════

  # T1: Drive-by on EPA channel (vehicular 40 km/h base + periodic obstruction).
  #     30s cycle: SINR swings 20→12→20 dB, Doppler 5→200→5 Hz, drops 0→2%→0.
  #     Stressed metrics: SINR (periodic dips), MCS (adapts each cycle),
  #       HARQ failures (burst at each obstruction), BSR (builds during bad phase),
  #       RLC UL delay (spikes at obstruction), PDCP throughput (periodic dip).
  #     Most telemetry-rich scenario — 6 full cycles in 180s.
  "T1|driveby_vehicular_epa|time_varying|--grc --fading --profile epa --snr 20 --doppler 70 --scenario drive-by --iperf-bitrate 25M|DRIVE-BY on EPA: Bus/truck blocks vehicular UE every 30s. SNR swings 20→12 dB, fd swings 70→200 Hz. 25M load causes BSR to build during each obstruction — SINR+MCS+HARQ+BSR+RLC all stressed."

  # T2: Drive-by on EPA + CW interference (urban pedestrian in interference zone).
  #     Base SNR=25 but SIR=15 dB (PIM interference) + drive-by shadow fading.
  #     Stressed metrics: SINR (both from interference and obstruction), MCS,
  #       HARQ failures (dual degradation source), asymmetric DL (CW on DL).
  #     Key value: CW interference + time-varying fading at same time.
  "T2|driveby_epa_interference|time_varying|--grc --fading --profile epa --snr 25 --doppler 5 --scenario drive-by --interference-type cw --sir 15 --iperf-bitrate 25M|DRIVE-BY + CW interference: PIM zone + periodic obstruction. SIR=15dB CW + 30s drive-by. 25M load stresses BSR during each dual-degradation phase."

  # T3: Urban walk on EPA (random stochastic SNR/Doppler — most realistic UE mobility).
  #     Random walk: SNR±10dB from base 22, Doppler 1-20 Hz, burst drops 15% of seconds.
  #     Stressed metrics: SINR (non-stationary), MCS (continuous re-adaptation),
  #       HARQ (random bursts), BSR (queue builds during bad patches), RLC delay.
  #     Key value: stochastic signal tests anomaly detector against non-periodic patterns.
  "T3|urban_walk_epa|time_varying|--grc --fading --profile epa --snr 22 --doppler 10 --scenario urban-walk --iperf-bitrate 25M|URBAN WALK on EPA: Random SNR walk ±10dB from 22dB, Doppler 1-20Hz. 25M load — stochastic BSR spikes when SNR dips constrain throughput."

  # T4: Edge-of-cell progressive decline on EPA (UE moving away from cell over 60s).
  #     SNR 28→12 dB linear, drop-prob 0→10% over 60s, then stays at floor.
  #     Stressed metrics: ALL metrics show progressive monotonic degradation:
  #       SINR declines, MCS ratchets down, HARQ failures increase, BSR grows,
  #       RLC delay increases, PDCP throughput collapses — clean degradation pattern.
  #     Key value: shows how each metric responds to systematic coverage loss.
  "T4|edge_of_cell_decline|time_varying|--grc --fading --profile epa --snr 28 --doppler 5 --scenario edge-of-cell --iperf-bitrate 25M|EDGE-OF-CELL on EPA: Linear SNR decline 28→12 dB over 60s. 25M load amplifies BSR growth as throughput collapses — clean multi-metric degradation across SINR+MCS+HARQ+BSR+RLC+PDCP."

  # T5: Urban walk on EVA (dense urban canyon with random mobility + frequency-selective fading).
  #     EVA delay spread provides significant multipath without ISI overflow.
  #     Random walk on top: SNR base 20 ±10 dB, Doppler 1-20 Hz, burst drops.
  #     Stressed metrics: HARQ failures (EVA multipath base + random bursts), MCS (low,
  #       highly variable), RLC delay (multipath-driven + random spikes), SINR (low base
  #       with random variation), BSR (persistent backlog + spikes).
  #     Key value: worst-case urban deployment with dynamic behaviour on top.
  "T5|urban_walk_eva_canyon|time_varying|--grc --fading --profile eva --snr 25 --doppler 10 --scenario urban-walk --iperf-bitrate 20M|URBAN WALK on EVA: Dense canyon multipath + random mobility. SNR raised to 25 for EVA stability. 20M load causes persistent BSR backlog + random spikes."

  # ══════════════════════════════════════════════════════════════════════════════
  # STEADY IMPAIRMENT — extreme steady-state operating points (3 scenarios)
  # Purpose: maximum impairment in specific failure modes for comparison.
  # These give clear upper bounds on anomaly magnitude for each failure type.
  # ══════════════════════════════════════════════════════════════════════════════

  # S1: Cell edge + CW interference — low SNR floor + neighbour-cell leakage.
  #     SNR=17 dB (not 12 — keeps UE connected), SIR=12 dB CW on DL, EPA.
  #     Stressed metrics: SINR (DL SINR ≈ 10 dB effective), MCS (stuck low 0-12),
  #       HARQ failures (persistent), PDCP DL throughput collapse.
  #     SNR=17 chosen: SNR=12 causes UE disconnect; 17 keeps it borderline stable.
  "S1|cell_edge_cw_interference|steady_impairment|--grc --fading --profile epa --snr 20 --doppler 5 --drop-prob 0.02 --interference-type cw --sir 15 --iperf-bitrate 20M|CELL EDGE + CW: SNR=20dB, SIR=15dB. Effective DL SINR ≈ 13dB. 20M load stresses BSR as scheduler capacity limited — persistent HARQ failures + DL throughput reduction."

  # S2: Rayleigh worst-case — complete NLoS, deep periodic nulls (basement/shielded).
  #     K=0 (pure scatter), SNR=28 dB, fd=5 Hz. SNR is high but Rayleigh nulls
  #     cause deep periodic fades that SNR alone cannot overcome.
  #     Stressed metrics: SINR (deep periodic nulls), HARQ failures (burst at nulls),
  #       MCS (high but interrupted), RLC delay spikes.
  #     ⚠ Duration capped at 90s — UE may disconnect after 2-3 min.
  "S2|rayleigh_deep_fade|steady_impairment|--grc --rayleigh --snr 28 --doppler 5|RAYLEIGH worst-case: Complete NLoS, all-scatter. SNR=28 but deep Rayleigh nulls cause bursty HARQ failures. Capped at 90s — UE may disconnect."

  # S3: High-speed train — extreme Doppler (fd=300 Hz) + EVA frequency-selective fading.
  #     f_d = 180 km/h × 1.667 = 300 Hz, coherence time ≈ 3.3 ms (3 TTIs).
  #     CSI always stale + frequency-selective fading + 5% drops = scheduler breakdown.
  #     Stressed metrics: MCS (near-random, cannot track channel), HARQ failures
  #       (maximum rate), PDCP throughput (near-zero), RLC delay (maximum).
  #     ⚠ May destabilize srsRAN UE — most extreme scenario.
  "S3|high_speed_train_epa|steady_impairment|--grc --fading --profile epa --snr 22 --doppler 300 --drop-prob 0.03 --iperf-bitrate 20M|HIGH-SPEED TRAIN: EPA-300, fd=300Hz, 3% drops. EPA (not EVA) for UE stability at extreme Doppler. 20M load — maximum MCS variance, HARQ failure rate, RLC delay."

  # ══════════════════════════════════════════════════════════════════════════════
  # RLF CYCLE SCENARIOS — Radio Link Failure injection (2 scenarios)
  #
  # 4-second complete blackout (drop_prob=1.0) every 90 seconds.
  # T310 timer = 1000ms → 4s blackout guarantees T310 expiry → RLF.
  # UE then: RACH preamble → RRC re-establishment (proc_id=3) → NGAP session resume.
  # Stresses schemas: rach_stats, rrc_ue_procedure, rrc_ue_add, ngap events.
  # Real fault analogue: intermittent feeder fault, power transient, interference burst.
  # 3GPP alarms: RRC.ConnReEstabSucc.Rate, RACH.PreambleTransmission.Count,
  #              radioLinkFailure (O1, TS 28.632).
  # ══════════════════════════════════════════════════════════════════════════════

  # L1: RLF cycle on clean channel — isolates the pure RACH+RRC signature.
  "L1|rlf_cycle_clean_channel|rlf_cycle|--grc --fading --k-factor 6 --snr 25 --doppler 2 --scenario rlf-cycle --iperf-bitrate 20M|RLF CYCLE (clean): 4s blackout every 90s on clean LoS. Isolates pure RACH+RRC re-establishment signature. BSR spike at each blackout, then rapid recovery."

  # L2: RLF cycle on degraded EPA — compounded fault (bad channel + RLF).
  "L2|rlf_cycle_degraded_epa|rlf_cycle|--grc --fading --profile epa --snr 20 --doppler 70 --scenario rlf-cycle --iperf-bitrate 25M|RLF CYCLE (degraded): 4s blackout every 90s on EPA vehicular. Compounded: elevated HARQ baseline + periodic RLF + RACH/RRC events — most realistic real-world fault signature."
)

# ── Helper: check if scenario ID is in the selection list ─────────────────────
is_selected() {
  local id="$1"
  [[ -z "$SELECTED_SCENARIOS" ]] && return 0
  echo ",$SELECTED_SCENARIOS," | grep -qi ",$id," && return 0
  return 1
}

# ── Per-scenario duration override (E2 Rayleigh capped at 90s) ────────────────
scenario_duration() {
  local id="$1"
  if [[ "$id" == "S2" ]]; then
    # Rayleigh: UE may disconnect after 2-3 min — cap at 90s
    echo $((DURATION < 90 ? DURATION : 90))
  else
    echo "$DURATION"
  fi
}

# ── Run one scenario ──────────────────────────────────────────────────────────
run_scenario() {
  local id="$1" label="$2" category="$3" flags="$4" description="$5"
  local logfile="$DATASET_DIR/${id}_${label}.log"
  local dur
  dur=$(scenario_duration "$id")

  banner "═══════════════════════════════════════════════════════════════"
  banner "  Scenario $id: $label"
  banner "  Category: $category"
  banner "  Flags: $flags"
  banner "  Collect: ${dur}s  Settle: ${SETTLE_TIME}s"
  banner "═══════════════════════════════════════════════════════════════"
  info "$description"
  echo ""

  if $DRY_RUN; then
    info "[DRY RUN] Would run: bash $LAUNCH_SCRIPT --no-grafana $flags"
    info "[DRY RUN] Output: $logfile"
    echo "$id,$label,$category,\"$flags\",\"$description\",dry_run,0,0,$logfile" >> "$DATASET_DIR/manifest.csv"
    return 0
  fi

  # Full pipeline teardown before each scenario launch — ensures no stale
  # ZMQ sockets (broker/gNB/UE) hold ports 2000/2001/4000/4001
  bash "$STOP_SCRIPT" 2>&1 | tail -2 || true
  sleep 2

  # Kill any lingering tee processes that might hold decoder.log open
  pkill -9 -f "tee.*/tmp/decoder.log" 2>/dev/null || true
  sleep 1

  # Clear decoder log
  > "$DECODER_LOG" 2>/dev/null || true

  # Launch pipeline (background — launch script blocks until stack is up)
  info "Launching pipeline with: --no-grafana $flags"
  bash "$LAUNCH_SCRIPT" --no-grafana $flags >/tmp/collect_channel_launch.log 2>&1 || true
  tail -5 /tmp/collect_channel_launch.log

  # Verify gNB started
  if ! pgrep -f "gnb" &>/dev/null; then
    fail "gNB did not start for scenario $id — skipping"
    echo "$id,$label,$category,\"$flags\",\"$description\",failed_start,0,0,$logfile" >> "$DATASET_DIR/manifest.csv"
    bash "$STOP_SCRIPT" 2>&1 | tail -3 || true
    sleep "$COOLDOWN"
    return 1
  fi

  # Settle period: wait for UE attach AND codelet load, up to SETTLE_TIME*2
  info "Waiting for UE attach + codelet load (max $((SETTLE_TIME * 2))s)..."
  local settle_waited=0
  local settle_max=$((SETTLE_TIME * 2))
  local codelets_ready=false
  while [[ $settle_waited -lt $settle_max ]]; do
    sleep 5
    settle_waited=$((settle_waited + 5))
    # Check UE alive
    if ! pgrep -f "srsue" &>/dev/null; then
      warn "UE not yet attached at ${settle_waited}s — waiting..."
      continue
    fi
    # Check that MAC codelets have loaded: look for crc_stats or bsr_stats in decoder log
    if grep -q '_schema_proto_msg.*crc_stats\|_schema_proto_msg.*bsr_stats' "$DECODER_LOG" 2>/dev/null; then
      codelets_ready=true
      ok "Codelets ready at ${settle_waited}s — starting collection"
      break
    fi
    printf "\r  Waiting for codelets... ${settle_waited}s elapsed"
  done
  echo ""

  if ! pgrep -f "srsue" &>/dev/null; then
    warn "UE failed to attach within settle period for scenario $id"
    echo "$id,$label,$category,\"$flags\",\"$description\",ue_no_attach,0,0,$logfile" >> "$DATASET_DIR/manifest.csv"
    bash "$STOP_SCRIPT" 2>&1 | tail -3 || true
    sleep "$COOLDOWN"
    return 1
  fi

  if ! $codelets_ready; then
    warn "MAC codelets did not load within ${settle_max}s for scenario $id — telemetry will be incomplete"
  fi

  # NOTE: decoder log is NOT reset here — preserves attach-phase events so
  # time-varying scenarios (edge-of-cell, drive-by) capture data from pipeline
  # start. relative_s in export anchors to first timestamp so timing is accurate.

  # Collect telemetry
  local collect_start
  collect_start=$(date +%s)
  info "Collecting telemetry for ${dur}s..."

  local elapsed=0
  local ue_alive=true
  while [[ $elapsed -lt $dur ]]; do
    sleep 5
    elapsed=$((elapsed + 5))
    if ! pgrep -f "srsue" &>/dev/null; then
      warn "UE crashed/disconnected at ${elapsed}s"
      ue_alive=false
      break
    fi
    local pct=$((elapsed * 100 / dur))
    printf "\r  [%3d%%] %ds/%ds  UE: alive" "$pct" "$elapsed" "$dur"
  done
  echo ""

  local collect_end
  collect_end=$(date +%s)
  local actual_dur=$((collect_end - collect_start))

  # Count telemetry lines
  local line_count=0
  [[ -f "$DECODER_LOG" ]] && line_count=$(wc -l < "$DECODER_LOG")

  # Determine status
  local status="complete"
  if ! $ue_alive; then
    status="ue_crashed"
  elif [[ $line_count -eq 0 ]]; then
    status="no_data"
  fi

  # Save log
  if [[ $line_count -gt 0 ]]; then
    cp "$DECODER_LOG" "$logfile"
    ok "Saved $line_count telemetry lines → $(basename "$logfile")"
  else
    warn "No telemetry data for scenario $id"
  fi

  # Manifest entry
  echo "$id,$label,$category,\"$flags\",\"$description\",$status,$actual_dur,$line_count,$logfile" >> "$DATASET_DIR/manifest.csv"

  # Export this scenario's log to CSV/HDF5
  if [[ $line_count -gt 0 ]]; then
    info "Exporting telemetry → CSV + HDF5..."
    python3 "$HOME/Desktop/export_channel_dataset.py" "$DATASET_DIR" --format both \
      2>&1 | grep -E "^\[|CSV|HDF5|rows|ERROR" || true
  fi

  # Teardown
  info "Stopping pipeline..."
  bash "$STOP_SCRIPT" 2>&1 | tail -3 || true

  # Cooldown
  info "Cooldown ${COOLDOWN}s..."
  sleep "$COOLDOWN"

  ok "Scenario $id done: status=$status  duration=${actual_dur}s  lines=$line_count"
  return 0
}

# ── Main ──────────────────────────────────────────────────────────────────────
banner ""
banner "╔══════════════════════════════════════════════════════════════╗"
banner "║   Realistic Channel Dataset Collection                      ║"
banner "║   10 real-world-grounded 5G scenarios (GRC broker)          ║"
banner "╚══════════════════════════════════════════════════════════════╝"
banner ""

mkdir -p "$DATASET_DIR"
info "Output directory: $DATASET_DIR"
info "Duration per scenario: ${DURATION}s (E2 Rayleigh capped at 90s)"
info "Settle time: ${SETTLE_TIME}s  |  Cooldown: ${COOLDOWN}s"
echo ""

# Count and estimate
total=0
for S in "${SCENARIOS[@]}"; do
  IFS='|' read -r id label category flags description <<< "$S"
  is_selected "$id" && total=$((total + 1))
done
info "Scenarios selected: $total"
est_min=$(( (total * (DURATION + SETTLE_TIME + COOLDOWN)) / 60 ))
info "Estimated runtime: ~${est_min} minutes"
echo ""

# Manifest header
echo "id,label,category,flags,description,status,duration_s,lines,logfile" > "$DATASET_DIR/manifest.csv"

# ── Scenario loop ─────────────────────────────────────────────────────────────
run_count=0
failed_count=0

for S in "${SCENARIOS[@]}"; do
  IFS='|' read -r id label category flags description <<< "$S"

  if ! is_selected "$id"; then
    continue
  fi

  run_count=$((run_count + 1))
  info "─── [$run_count/$total] Starting scenario $id ───────────────────────────"

  if run_scenario "$id" "$label" "$category" "$flags" "$description"; then
    ok "[$run_count/$total] $id complete"
  else
    failed_count=$((failed_count + 1))
    warn "[$run_count/$total] $id failed — continuing to next scenario"
  fi

  echo ""
done

# ── Summary ───────────────────────────────────────────────────────────────────
banner ""
banner "╔══════════════════════════════════════════════════════════════╗"
banner "║   Collection Complete                                        ║"
banner "╚══════════════════════════════════════════════════════════════╝"
banner ""

{
  echo "Realistic Channel Dataset — Collection Summary"
  echo "==============================================="
  echo "Date: $(date)"
  echo "Duration per scenario: ${DURATION}s (E2 capped at 90s)"
  echo "Scenarios run: $run_count  |  Failed: $failed_count"
  echo ""
  echo "Scenario results:"
  echo "-----------------"
  printf "  %-4s  %-35s %-12s %6s %8s  %s\n" "ID" "Label" "Category" "Dur(s)" "Lines" "Status"
  printf "  %-4s  %-35s %-12s %6s %8s  %s\n" "----" "-----------------------------------" "------------" "------" "--------" "------"
  tail -n +2 "$DATASET_DIR/manifest.csv" | while IFS=, read -r sid slabel scat _flags _desc sstatus sdur slines _log; do
    printf "  %-4s  %-35s %-12s %6s %8s  %s\n" "$sid" "$slabel" "$scat" "$sdur" "$slines" "$sstatus"
  done
  echo ""
  echo "Log files:"
  ls -lh "$DATASET_DIR/"*.log 2>/dev/null || echo "  (none)"
  echo ""
  echo "Total dataset size: $(du -sh "$DATASET_DIR" | cut -f1)"
} | tee "$DATASET_DIR/summary.txt"

echo ""
info "Manifest: $DATASET_DIR/manifest.csv"
info "Summary:  $DATASET_DIR/summary.txt"
echo ""
info "Structured dataset files:"
echo "  CSV : $DATASET_DIR/csv/<schema>.csv"
echo "  HDF5: $DATASET_DIR/channel_dataset.h5"
echo ""
info "Next step — generate comparison plots:"
echo "  python3 ~/Desktop/plot_channel_comparison.py $DATASET_DIR"
echo ""
info "Or replay a single log into InfluxDB:"
echo "  python3 ~/Desktop/telemetry_to_influxdb.py --replay <log> --db channel_dataset"
