#!/usr/bin/env bash
# =============================================================================
#  Anomalous Dataset Collection Script
#
#  Systematically runs the srsRAN pipeline under various channel conditions
#  to produce a labeled dataset of normal + anomalous performance samples.
#
#  Each scenario runs for a configurable duration, collects decoder logs,
#  and saves them with descriptive filenames and a manifest CSV.
#
#  Scenarios include:
#    - Baseline (AWGN-only, various SNR levels)
#    - Rician fading (different K-factors and Doppler)
#    - Rayleigh fading (deep nulls)
#    - GNU Radio channel broker: Rician/Rayleigh + AWGN with real-time viz
#    - High-mobility (vehicular Doppler)
#    - Extreme conditions (very low SNR, combined impairments)
#
#  Usage:
#    ./collect_anomalous_data.sh                    # Run all scenarios
#    ./collect_anomalous_data.sh --duration 120     # 2 min per scenario
#    ./collect_anomalous_data.sh --only-grc         # Only GNU Radio scenarios
#    ./collect_anomalous_data.sh --scenarios 1,2,5  # Run specific scenarios
#    ./collect_anomalous_data.sh --dry-run           # Show what would run
#
#  Output:
#    ~/Desktop/dataset/<timestamp>/
#      ├── manifest.csv         (scenario metadata)
#      ├── 01_baseline_snr30.log
#      ├── 02_baseline_snr28.log
#      ├── ...
#      └── summary.txt
# =============================================================================
set -uo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
DURATION=180           # seconds per scenario (3 min default)
SETTLE_TIME=30         # seconds to wait after pipeline starts before collecting
COOLDOWN=10            # seconds between scenarios
DATASET_DIR="$HOME/Desktop/dataset/$(date +%Y%m%d_%H%M%S)"
LAUNCH_SCRIPT="$HOME/Desktop/launch_mac_telemetry.sh"
STOP_SCRIPT="$HOME/Desktop/stop_mac_telemetry.sh"
DECODER_LOG="/tmp/decoder.log"
DRY_RUN=false
ONLY_GRC=false
SELECTED_SCENARIOS=""

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${CYAN}[COLLECT]${NC}  $*"; }
ok()    { echo -e "${GREEN}[  OK   ]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[ WARN  ]${NC}  $*"; }
fail()  { echo -e "${RED}[ FAIL  ]${NC}  $*"; }
banner(){ echo -e "${BOLD}${CYAN}$*${NC}"; }

# ── Parse flags ──────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration)    DURATION="$2"; shift ;;
    --duration=*)  DURATION="${1#*=}" ;;
    --settle)      SETTLE_TIME="$2"; shift ;;
    --cooldown)    COOLDOWN="$2"; shift ;;
    --only-grc)    ONLY_GRC=true ;;
    --scenarios)   SELECTED_SCENARIOS="$2"; shift ;;
    --scenarios=*) SELECTED_SCENARIOS="${1#*=}" ;;
    --dry-run)     DRY_RUN=true ;;
    --output)      DATASET_DIR="$2"; shift ;;
    -h|--help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --duration N     Seconds per scenario (default: $DURATION)"
      echo "  --settle N       Settle time after launch (default: $SETTLE_TIME)"
      echo "  --cooldown N     Cooldown between scenarios (default: $COOLDOWN)"
      echo "  --only-grc       Only run GNU Radio channel scenarios"
      echo "  --scenarios N,M  Run only listed scenario numbers (comma-separated)"
      echo "  --dry-run        Show scenarios without running"
      echo "  --output DIR     Output directory (default: ~/Desktop/dataset/<timestamp>)"
      echo "  -h, --help       Show this help"
      exit 0 ;;
    *) warn "Unknown flag: $1" ;;
  esac
  shift
done

# ── Scenario Definitions ─────────────────────────────────────────────────────
# Format: "ID|LABEL|CATEGORY|LAUNCH_FLAGS|DESCRIPTION"
# Categories: baseline, degraded, fading, extreme, grc_fading, grc_impairment
SCENARIOS=(
  # ── Baselines (normal operation) ──
  "01|baseline_snr30|baseline|--snr 30|AWGN only SNR=30dB (clean channel)"
  "02|baseline_snr28|baseline|--snr 28|AWGN only SNR=28dB (tuned baseline)"
  "03|baseline_perfect|baseline|--no-broker|Perfect channel (no impairments)"

  # ── Mild degradation (should show elevated HARQ but stable) ──
  "04|mild_snr25|degraded|--snr 25|AWGN SNR=25dB (elevated HARQ retx)"
  "05|mild_fading_k6|degraded|--fading --k-factor 6 --snr 28|Rician K=6dB gentle fading"
  "06|mild_fading_k3|degraded|--fading --k-factor 3 --snr 28|Rician K=3dB moderate fading"

  # ── Stressed conditions (HARQ failures, possible connectivity issues) ──
  "07|stress_snr22|fading|--snr 22|AWGN SNR=22dB (frequent NACK/DTX)"
  "08|stress_fading_k1|fading|--fading --k-factor 1 --snr 25|Rician K=1dB heavy fading + noise"
  "09|stress_rayleigh|fading|--rayleigh --snr 28|Rayleigh fading (deep nulls at SNR=28)"
  "10|stress_rayleigh_noisy|fading|--rayleigh --snr 22|Rayleigh + low SNR (very harsh)"
  "11|stress_fast_fading|fading|--fading --k-factor 3 --doppler 30 --snr 25|Fast Doppler=30Hz + noise"

  # ── GNU Radio: frequency-selective fading (EPA/EVA/ETU) ──
  "12|grc_epa_pedestrian|grc_fading|--grc --fading --profile epa --doppler 5 --snr 25|EPA profile pedestrian"
  "13|grc_epa_vehicular|grc_fading|--grc --fading --profile epa --doppler 70 --snr 25|EPA profile vehicular"
  "14|grc_eva_pedestrian|grc_fading|--grc --fading --profile eva --doppler 5 --snr 25|EVA profile pedestrian"
  "15|grc_eva_vehicular|grc_fading|--grc --fading --profile eva --doppler 70 --snr 25|EVA profile vehicular"
  "16|grc_etu_pedestrian|grc_fading|--grc --fading --profile etu --doppler 5 --snr 25|ETU profile pedestrian"
  "17|grc_etu_vehicular|grc_fading|--grc --fading --profile etu --doppler 70 --snr 25|ETU profile vehicular"

  # ── GNU Radio: additional stressed fading scenarios ──
  "18|grc_rician_k1_noisy|grc_fading|--grc --fading --k-factor 1 --doppler 10 --snr 23|GRC Rician K=1 Doppler=10Hz SNR=23"
  "19|grc_rayleigh_moderate|grc_fading|--grc --fading --rayleigh --doppler 10 --snr 25|GRC Rayleigh Doppler=10Hz SNR=25"
  "20|grc_rician_vehicular|grc_fading|--grc --fading --k-factor 3 --doppler 70 --snr 22|GRC Rician vehicular Doppler=70Hz SNR=22"

  # ── Extreme (likely to cause connection drops / UE crashes) ──
  "21|extreme_snr18|extreme|--snr 18|AWGN SNR=18dB (near UE failure threshold)"
  "22|extreme_snr15|extreme|--snr 15|AWGN SNR=15dB (UE will likely disconnect)"
  "23|extreme_rayleigh_fast|extreme|--rayleigh --doppler 70 --snr 22|Rayleigh + vehicular Doppler + noise"
  "24|grc_extreme_etu_fast|extreme|--grc --fading --profile etu --doppler 300 --snr 20 --rayleigh|ETU Rayleigh 300Hz Doppler (extreme)"
)

# ── Functions ────────────────────────────────────────────────────────────────
is_selected() {
  local id="$1"
  if [[ -z "$SELECTED_SCENARIOS" ]]; then
    return 0  # All selected
  fi
  local num="${id#0}"  # strip leading zero
  echo ",$SELECTED_SCENARIOS," | grep -q ",$num," && return 0
  echo ",$SELECTED_SCENARIOS," | grep -q ",$id," && return 0
  return 1
}

is_grc_scenario() {
  local flags="$1"
  echo "$flags" | grep -q '\-\-grc\|--profile'
}

run_scenario() {
  local id="$1" label="$2" category="$3" flags="$4" description="$5"
  local logfile="$DATASET_DIR/${id}_${label}.log"

  banner "═══════════════════════════════════════════════════════"
  banner "  Scenario $id: $label"
  banner "  Category: $category"
  banner "  Flags: $flags"
  banner "  Description: $description"
  banner "═══════════════════════════════════════════════════════"

  if $DRY_RUN; then
    info "[DRY RUN] Would run: $LAUNCH_SCRIPT $flags"
    info "[DRY RUN] Output: $logfile"
    echo "$id,$label,$category,\"$flags\",\"$description\",dry_run,0,0,$logfile" >> "$DATASET_DIR/manifest.csv"
    return 0
  fi

  # Clear previous decoder log
  > "$DECODER_LOG" 2>/dev/null || true

  # Launch pipeline
  local start_ts
  start_ts=$(date +%s)
  info "Launching pipeline..."
  bash "$LAUNCH_SCRIPT" --no-grafana $flags 2>&1 | tail -5 || true

  # Check if pipeline is up
  if ! pgrep -f "gnb" &>/dev/null; then
    fail "Pipeline failed to start for scenario $id"
    echo "$id,$label,$category,\"$flags\",\"$description\",failed,0,0,$logfile" >> "$DATASET_DIR/manifest.csv"
    bash "$STOP_SCRIPT" 2>&1 | tail -3 || true
    sleep "$COOLDOWN"
    return 1
  fi

  # Settle period (let pipeline stabilize)
  info "Settling for ${SETTLE_TIME}s..."
  sleep "$SETTLE_TIME"

  # Mark collection start
  local collect_start
  collect_start=$(date +%s)
  info "Collecting telemetry for ${DURATION}s..."

  # Wait for collection duration
  local elapsed=0
  while [[ $elapsed -lt $DURATION ]]; do
    sleep 10
    elapsed=$((elapsed + 10))
    # Check if UE is still alive
    if ! pgrep -f "srsue" &>/dev/null; then
      warn "UE crashed at ${elapsed}s — marking as anomalous dropout"
      break
    fi
    # Progress
    local pct=$((elapsed * 100 / DURATION))
    printf "\r  [%3d%%] %d/%ds collected..." "$pct" "$elapsed" "$DURATION"
  done
  echo ""

  local collect_end
  collect_end=$(date +%s)
  local actual_duration=$((collect_end - collect_start))

  # Count collected lines
  local line_count=0
  if [[ -f "$DECODER_LOG" ]]; then
    line_count=$(wc -l < "$DECODER_LOG")
  fi

  # Check if UE survived
  local status="complete"
  if ! pgrep -f "srsue" &>/dev/null; then
    status="ue_crashed"
    warn "UE did not survive scenario $id"
  fi

  # Save log
  if [[ -f "$DECODER_LOG" ]] && [[ $line_count -gt 0 ]]; then
    cp "$DECODER_LOG" "$logfile"
    ok "Saved $line_count lines to $(basename "$logfile")"
  else
    warn "No telemetry data collected for scenario $id"
    status="no_data"
  fi

  # Record in manifest
  echo "$id,$label,$category,\"$flags\",\"$description\",$status,$actual_duration,$line_count,$logfile" >> "$DATASET_DIR/manifest.csv"

  # Teardown
  info "Stopping pipeline..."
  bash "$STOP_SCRIPT" 2>&1 | tail -3 || true

  # Cooldown
  info "Cooldown ${COOLDOWN}s..."
  sleep "$COOLDOWN"

  ok "Scenario $id complete: $status, ${actual_duration}s, $line_count lines"
  return 0
}

# ── Main ─────────────────────────────────────────────────────────────────────
banner ""
banner "╔═══════════════════════════════════════════════════════╗"
banner "║     Anomalous Dataset Collection                      ║"
banner "╚═══════════════════════════════════════════════════════╝"
banner ""

# Create output directory
mkdir -p "$DATASET_DIR"
info "Output directory: $DATASET_DIR"
info "Duration per scenario: ${DURATION}s"
info "Settle time: ${SETTLE_TIME}s"

# Count scenarios to run
total=0
for S in "${SCENARIOS[@]}"; do
  IFS='|' read -r id label category flags description <<< "$S"
  if ! is_selected "$id"; then continue; fi
  if $ONLY_GRC && ! is_grc_scenario "$flags"; then continue; fi
  total=$((total + 1))
done
info "Scenarios to run: $total"

# Estimate time
est_minutes=$(( (total * (DURATION + SETTLE_TIME + COOLDOWN)) / 60 ))
info "Estimated total time: ~${est_minutes} minutes"
echo ""

# Write manifest header
echo "id,label,category,flags,description,status,duration_s,lines,logfile" > "$DATASET_DIR/manifest.csv"

# Run scenarios
completed=0
failed=0
for S in "${SCENARIOS[@]}"; do
  IFS='|' read -r id label category flags description <<< "$S"

  if ! is_selected "$id"; then continue; fi
  if $ONLY_GRC && ! is_grc_scenario "$flags"; then continue; fi

  completed=$((completed + 1))
  info "Running scenario $completed/$total..."

  if run_scenario "$id" "$label" "$category" "$flags" "$description"; then
    ok "[$completed/$total] Scenario $id passed"
  else
    failed=$((failed + 1))
    warn "[$completed/$total] Scenario $id failed"
  fi
done

# ── Summary ──────────────────────────────────────────────────────────────────
banner ""
banner "╔═══════════════════════════════════════════════════════╗"
banner "║     Collection Complete                               ║"
banner "╚═══════════════════════════════════════════════════════╝"
banner ""

# Write summary
{
  echo "Anomalous Dataset Collection Summary"
  echo "====================================="
  echo "Date: $(date)"
  echo "Duration per scenario: ${DURATION}s"
  echo "Total scenarios: $total"
  echo "Completed: $((completed - failed))"
  echo "Failed: $failed"
  echo ""
  echo "Scenario Results:"
  echo "-----------------"
  tail -n +2 "$DATASET_DIR/manifest.csv" | while IFS=, read -r sid slabel scat sflags sdesc sstatus sdur slines slog; do
    printf "  %-4s %-30s %-15s %6ss %8s lines  [%s]\n" "$sid" "$slabel" "$scat" "$sdur" "$slines" "$sstatus"
  done
  echo ""
  echo "Files:"
  ls -lh "$DATASET_DIR"/*.log 2>/dev/null || echo "  (no log files)"
  echo ""
  echo "Total dataset size: $(du -sh "$DATASET_DIR" | cut -f1)"
} | tee "$DATASET_DIR/summary.txt"

echo ""
info "Manifest: $DATASET_DIR/manifest.csv"
info "Summary:  $DATASET_DIR/summary.txt"
info "Log files: $DATASET_DIR/*.log"
echo ""
info "To ingest all logs into InfluxDB:"
echo "  for f in $DATASET_DIR/*.log; do"
echo "    python3 ~/Desktop/telemetry_to_influxdb.py --replay \"\$f\" --db dataset_\$(basename \"\$f\" .log)"
echo "  done"
