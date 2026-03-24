#!/usr/bin/env python3
"""
sweep_broker_params.py — Live pipeline parameter sweep for srsRAN channel broker.

For each preset:
  1. Start the pipeline via launch_mac_telemetry.sh with broker params
  2. Wait for UE attach (up to --attach-timeout seconds)
  3. Run for --duration seconds, sampling health every 5s
  4. Stop the pipeline via stop_mac_telemetry.sh
  5. Report: STABLE / DEGRADED / CRASHED + key metrics

Usage:
    python3 sweep_broker_params.py                          # all presets, 60s each
    python3 sweep_broker_params.py --duration 90            # longer per preset
    python3 sweep_broker_params.py --presets stable,mild    # specific presets
    python3 sweep_broker_params.py --list                   # list preset names
    python3 sweep_broker_params.py --output results.json    # save JSON results
"""

import subprocess
import time
import json
import re
import sys
import os
import argparse
from datetime import datetime
from pathlib import Path

DESKTOP     = Path.home() / "Desktop"
LAUNCH      = DESKTOP / "launch_mac_telemetry.sh"
STOP        = DESKTOP / "stop_mac_telemetry.sh"
DECODER_LOG = Path("/tmp/decoder.log")

POLL_INTERVAL   = 5     # seconds between health checks during run
ATTACH_TIMEOUT  = 90    # seconds to wait for UE to attach
POST_STOP_WAIT  = 8     # seconds after stop before next preset

# ── Preset definitions ────────────────────────────────────────────────────────
# Each preset maps to launch_mac_telemetry.sh arguments.
# 'expected' is informational only — used in the report.

PRESETS = {
    "stable": {
        "desc": "Baseline (Rician, SNR=28 dB, fd=5 Hz)",
        "args": ["--snr", "28", "--k-factor", "3", "--doppler", "5",
                 "--grc", "--fading"],
        "expected": "STABLE",
    },
    "mild": {
        "desc": "Mild stress (EPA 7-tap, SNR=20 dB, fd=10 Hz)",
        "args": ["--snr", "20", "--k-factor", "3", "--doppler", "10",
                 "--grc", "--profile", "epa"],
        "expected": "STABLE",
    },
    "mild-cfo": {
        "desc": "Mild + CFO 100 Hz (Rician, SNR=25 dB)",
        "args": ["--snr", "25", "--k-factor", "3", "--doppler", "5",
                 "--grc", "--fading", "--cfo", "100"],
        "expected": "STABLE",
    },
    "moderate": {
        "desc": "Moderate stress (EVA 9-tap, SNR=15 dB, fd=70 Hz, drop=2%)",
        "args": ["--snr", "15", "--k-factor", "1", "--doppler", "70",
                 "--grc", "--profile", "eva", "--drop-prob", "0.02"],
        "expected": "DEGRADED",
    },
    "heavy": {
        "desc": "Heavy stress (ETU 9-tap, SNR=10 dB, fd=200 Hz, CFO=100 Hz, drop=10%)",
        "args": ["--snr", "10", "--doppler", "200",
                 "--grc", "--profile", "etu", "--cfo", "100", "--drop-prob", "0.10"],
        "expected": "DEGRADED",
    },
    "rayleigh": {
        "desc": "Flat Rayleigh (SNR=25 dB, fd=5 Hz) — ~3 min UE lifetime",
        "args": ["--snr", "25", "--doppler", "5", "--grc", "--rayleigh"],
        "expected": "CRASH",
    },
    "low-snr": {
        "desc": "Very low SNR (SNR=8 dB, Rician, fd=5 Hz) — UE likely drops",
        "args": ["--snr", "8", "--k-factor", "3", "--doppler", "5",
                 "--grc", "--fading"],
        "expected": "CRASH",
    },
    "high-drop": {
        "desc": "High drop rate (25%, SNR=28 dB, Rician) — RLC exhaustion risk",
        "args": ["--snr", "28", "--k-factor", "3", "--doppler", "5",
                 "--grc", "--fading", "--drop-prob", "0.25"],
        "expected": "CRASH",
    },
    "cfo-500": {
        "desc": "Max CFO (500 Hz, SNR=28 dB, Rician) — sync stress",
        "args": ["--snr", "28", "--k-factor", "3", "--doppler", "5",
                 "--grc", "--fading", "--cfo", "500"],
        "expected": "DEGRADED",
    },
    "high-doppler": {
        "desc": "High Doppler (fd=200 Hz, Rician, SNR=28 dB) — fast fading",
        "args": ["--snr", "28", "--k-factor", "3", "--doppler", "200",
                 "--grc", "--fading"],
        "expected": "DEGRADED",
    },
}

# ── Colors ────────────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def color_status(status):
    c = {"STABLE": GREEN, "DEGRADED": YELLOW, "CRASHED": RED, "NO_ATTACH": RED}.get(status, "")
    return f"{c}{status}{RESET}"

def info(msg):  print(f"  {CYAN}•{RESET} {msg}")
def ok(msg):    print(f"  {GREEN}✓{RESET} {msg}")
def warn(msg):  print(f"  {YELLOW}△{RESET} {msg}")
def err(msg):   print(f"  {RED}✗{RESET} {msg}")
def hdr(msg):   print(f"\n{BOLD}{msg}{RESET}")


# ── Process helpers ───────────────────────────────────────────────────────────

def pid_of(name):
    """Return list of PIDs matching process name."""
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", name], text=True).strip()
        return [int(p) for p in out.split() if p]
    except subprocess.CalledProcessError:
        return []

def is_running(name):
    return len(pid_of(name)) > 0


# ── Log parsing ───────────────────────────────────────────────────────────────

def log_position():
    """Return current end-of-file byte position in decoder.log."""
    try:
        return DECODER_LOG.stat().st_size
    except FileNotFoundError:
        return 0

def read_new_log(start_pos):
    """Return new lines added to decoder.log since start_pos."""
    try:
        with open(DECODER_LOG, "rb") as f:
            f.seek(start_pos)
            data = f.read()
        return data.decode("utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return []

REC_RE = re.compile(r'REC: (.*?)"?\s*$')

def parse_log_lines(lines):
    """Parse decoder.log lines → list of dicts (schema messages)."""
    msgs = []
    for line in lines:
        m = REC_RE.search(line)
        if not m:
            continue
        raw = m.group(1).strip().rstrip('"')
        try:
            msgs.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    return msgs

def compute_metrics(msgs, elapsed_secs):
    """Derive health metrics from a list of parsed telemetry messages."""
    metrics = {
        "total_msgs":      len(msgs),
        "msg_rate":        round(len(msgs) / max(elapsed_secs, 1), 2),
        "rrc_ue_add":      0,
        "rrc_ue_remove":   0,
        "crc_ok":          0,
        "crc_ko":          0,
        "bler_pct":        None,
        "harq_dl_fail":    0,
        "harq_ul_fail":    0,
        "schemas_seen":    set(),
    }
    # Cumulative CRC tracking (take last value, diff from zero)
    last_crc = {}
    for msg in msgs:
        schema = msg.get("_schema_proto_msg", "")
        metrics["schemas_seen"].add(schema)

        if schema == "rrc_ue_add":
            metrics["rrc_ue_add"] += 1
        elif schema == "rrc_ue_remove":
            metrics["rrc_ue_remove"] += 1

        elif schema == "crc_stats":
            # Differentiate MAC vs FAPI by package name
            pkg = msg.get("_schema_proto_package", "")
            if "mac" in pkg or "mac_sched" in pkg:
                last_crc["ok"] = msg.get("numCrcOk", last_crc.get("ok", 0))
                last_crc["ko"] = msg.get("numCrcKo", last_crc.get("ko", 0))

        elif schema == "harq_stats":
            # Take max seen (cumulative counters)
            metrics["harq_dl_fail"] = max(
                metrics["harq_dl_fail"],
                msg.get("numHarqDlNok", 0))
            metrics["harq_ul_fail"] = max(
                metrics["harq_ul_fail"],
                msg.get("numHarqUlNok", 0))

    if last_crc:
        total = last_crc.get("ok", 0) + last_crc.get("ko", 0)
        if total > 0:
            metrics["crc_ok"]   = last_crc.get("ok", 0)
            metrics["crc_ko"]   = last_crc.get("ko", 0)
            metrics["bler_pct"] = round(100.0 * last_crc.get("ko", 0) / total, 2)

    metrics["schemas_seen"] = sorted(metrics["schemas_seen"])
    return metrics


def classify(metrics, attach_ok, ue_alive_end, broker_alive_end, duration):
    """Return (status, reason) based on collected metrics."""
    if not attach_ok:
        return "NO_ATTACH", "UE never attached within timeout"
    if not broker_alive_end:
        return "CRASHED", "Broker process died"
    if not ue_alive_end:
        return "CRASHED", "srsUE process died (UE disconnected)"
    if metrics["rrc_ue_remove"] > 0:
        return "CRASHED", f"RRC UE remove event seen ({metrics['rrc_ue_remove']}x)"

    bler = metrics.get("bler_pct")
    harq_fail = metrics["harq_dl_fail"] + metrics["harq_ul_fail"]

    if bler is None:
        # No CRC stats — maybe not enough time
        if metrics["msg_rate"] < 1.0:
            return "DEGRADED", "Very low telemetry rate — possible instability"
        return "STABLE", "No CRC data yet (short run?)"

    if bler > 30.0:
        return "CRASHED", f"BLER {bler:.1f}% — link effectively broken"
    if bler > 10.0 or harq_fail > 50:
        return "DEGRADED", f"BLER {bler:.1f}%, HARQ failures {harq_fail}"
    return "STABLE", f"BLER {bler:.1f}%, HARQ failures {harq_fail}"


# ── Pipeline control ──────────────────────────────────────────────────────────

def stop_pipeline():
    """Run stop script and wait for processes to die."""
    info("Stopping pipeline...")
    try:
        subprocess.run(
            ["bash", str(STOP)],
            timeout=30, capture_output=True)
    except Exception as e:
        warn(f"stop script error: {e}")
    # Wait for processes to die
    deadline = time.time() + 15
    while time.time() < deadline:
        if not is_running("gnb") and not is_running("srsue"):
            break
        time.sleep(1)
    time.sleep(POST_STOP_WAIT)


def wait_for_attach(start_pos, timeout):
    """Poll decoder.log for rrc_ue_add event. Returns (attached, elapsed)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        lines  = read_new_log(start_pos)
        msgs   = parse_log_lines(lines)
        for m in msgs:
            if m.get("_schema_proto_msg") == "rrc_ue_add":
                return True, round(time.time() - t0, 1)
        time.sleep(2)
    return False, timeout


# ── Single preset run ─────────────────────────────────────────────────────────

def run_preset(name, preset, duration, attach_timeout, no_grafana, no_traffic):
    hdr(f"Preset: {name}")
    print(f"  {preset['desc']}")
    print(f"  Expected: {preset['expected']}   Duration: {duration}s")
    print(f"  Args: {' '.join(preset['args'])}")
    print()

    result = {
        "preset":   name,
        "desc":     preset["desc"],
        "expected": preset["expected"],
        "args":     preset["args"],
        "timestamp": datetime.now().isoformat(),
        "duration":  duration,
        "status":   None,
        "reason":   None,
        "metrics":  {},
        "samples":  [],
    }

    # Clean up before starting
    stop_pipeline()

    log_start = log_position()

    # Build launch command
    cmd = ["bash", str(LAUNCH)] + preset["args"] + ["--no-gui"]
    if no_grafana:
        cmd.append("--no-grafana")
    if no_traffic:
        cmd.append("--no-traffic")

    info(f"Starting pipeline: {' '.join(cmd[2:])}")
    launch_proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for UE attach
    info(f"Waiting for UE attach (up to {attach_timeout}s)...")
    attached, attach_elapsed = wait_for_attach(log_start, attach_timeout)

    if attached:
        ok(f"UE attached in {attach_elapsed}s")
        result["attach_elapsed"] = attach_elapsed
    else:
        err(f"UE did not attach within {attach_timeout}s")
        result["attach_elapsed"] = None

    # Run for duration, sampling health
    info(f"Running for {duration}s...")
    run_start     = time.time()
    sample_times  = []
    sample_data   = []

    while time.time() - run_start < duration:
        elapsed = time.time() - run_start
        gnb_up    = is_running("gnb")
        ue_up     = is_running("srsue")
        broker_up = is_running("srsran_channel_broker")
        iperf_up  = is_running("iperf3")

        lines  = read_new_log(log_start)
        msgs   = parse_log_lines(lines)
        sample = compute_metrics(msgs, elapsed)

        sample_times.append(round(elapsed, 1))
        sample_data.append({
            "t":          round(elapsed, 1),
            "gnb_up":     gnb_up,
            "ue_up":      ue_up,
            "broker_up":  broker_up,
            "iperf_up":   iperf_up,
            "msg_rate":   sample["msg_rate"],
            "bler_pct":   sample["bler_pct"],
            "harq_dl_fail": sample["harq_dl_fail"],
        })

        # Print live sample
        bler_str = f"{sample['bler_pct']:.1f}%" if sample["bler_pct"] is not None else "N/A"
        proc_str = f"gNB:{'Y' if gnb_up else 'N'} UE:{'Y' if ue_up else 'N'} broker:{'Y' if broker_up else 'N'}"
        print(f"    t={elapsed:5.0f}s  msgs/s={sample['msg_rate']:5.1f}  "
              f"BLER={bler_str:>6}  HARQ_fail={sample['harq_dl_fail']:4d}  [{proc_str}]")

        # Early exit if everything is dead
        if not gnb_up and not ue_up and not broker_up:
            err("All processes died — stopping early")
            break

        next_tick = run_start + len(sample_times) * POLL_INTERVAL
        sleep_for = max(0, next_tick - time.time())
        time.sleep(sleep_for)

    # Final state
    actual_elapsed  = time.time() - run_start
    ue_alive_end    = is_running("srsue")
    broker_alive_end = is_running("srsran_channel_broker")

    # Full metrics over entire window
    all_lines   = read_new_log(log_start)
    all_msgs    = parse_log_lines(all_lines)
    final_metrics = compute_metrics(all_msgs, actual_elapsed)

    status, reason = classify(
        final_metrics, attached, ue_alive_end, broker_alive_end, duration)

    result["status"]  = status
    result["reason"]  = reason
    result["metrics"] = {k: v for k, v in final_metrics.items()
                         if k != "schemas_seen"}
    result["schemas_seen"] = final_metrics["schemas_seen"]
    result["samples"] = sample_data

    # Print result
    print()
    print(f"  ┌─ Result: {color_status(status)}")
    print(f"  │  Reason: {reason}")
    print(f"  │  Msgs:   {final_metrics['total_msgs']} total, "
          f"{final_metrics['msg_rate']}/s")
    bler = final_metrics["bler_pct"]
    if bler is not None:
        bler_c = GREEN if bler < 5 else (YELLOW if bler < 15 else RED)
        print(f"  │  BLER:   {bler_c}{bler:.2f}%{RESET}")
    harq = final_metrics["harq_dl_fail"] + final_metrics["harq_ul_fail"]
    print(f"  │  HARQ failures:  DL={final_metrics['harq_dl_fail']}  "
          f"UL={final_metrics['harq_ul_fail']}")
    print(f"  │  RRC events:     add={final_metrics['rrc_ue_add']}  "
          f"remove={final_metrics['rrc_ue_remove']}")
    print(f"  └─ Schemas seen: {', '.join(final_metrics['schemas_seen'][:6])}"
          + ("..." if len(final_metrics["schemas_seen"]) > 6 else ""))

    # Stop
    stop_pipeline()
    return result


# ── Summary table ─────────────────────────────────────────────────────────────

STATUS_SYMBOLS = {"STABLE": "✓", "DEGRADED": "△", "CRASHED": "✗", "NO_ATTACH": "✗"}

def print_summary(results):
    hdr("SWEEP SUMMARY")
    print(f"  {'Preset':<15} {'Status':<12} {'BLER':>6} {'HARQ_fail':>10} "
          f"{'msgs/s':>7}  Reason")
    print("  " + "─" * 80)
    for r in results:
        sym    = STATUS_SYMBOLS.get(r["status"], "?")
        status = r["status"] or "?"
        m      = r.get("metrics", {})
        bler   = f"{m['bler_pct']:.1f}%" if m.get("bler_pct") is not None else "N/A"
        harq   = m.get("harq_dl_fail", 0) + m.get("harq_ul_fail", 0)
        rate   = m.get("msg_rate", 0)
        c      = {"STABLE": GREEN, "DEGRADED": YELLOW}.get(status, RED)
        print(f"  {sym} {r['preset']:<13} {c}{status:<12}{RESET} {bler:>6} "
              f"{harq:>10}  {rate:>6.1f}  {r['reason']}")

    stable   = sum(1 for r in results if r["status"] == "STABLE")
    degraded = sum(1 for r in results if r["status"] == "DEGRADED")
    crashed  = sum(1 for r in results if r["status"] in ("CRASHED", "NO_ATTACH"))
    print(f"\n  Total: {len(results)}  "
          f"{GREEN}STABLE:{stable}{RESET}  "
          f"{YELLOW}DEGRADED:{degraded}{RESET}  "
          f"{RED}CRASHED/NO_ATTACH:{crashed}{RESET}")

    print(f"\n  SAFE VALUES (based on this run):")
    safe = [r["preset"] for r in results if r["status"] == "STABLE"]
    deg  = [r["preset"] for r in results if r["status"] == "DEGRADED"]
    bad  = [r["preset"] for r in results if r["status"] in ("CRASHED", "NO_ATTACH")]
    print(f"    Stable:   {', '.join(safe) if safe else 'none'}")
    print(f"    Degraded: {', '.join(deg)  if deg  else 'none'}")
    print(f"    Crash:    {', '.join(bad)  if bad  else 'none'}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Live pipeline sweep for srsRAN channel broker")
    parser.add_argument("--duration", type=int, default=60,
                        help="Seconds per preset after UE attaches (default: 60)")
    parser.add_argument("--attach-timeout", type=int, default=90,
                        help="Max seconds to wait for UE attach (default: 90)")
    parser.add_argument("--presets", type=str, default="all",
                        help="Comma-separated preset names, or 'all' (default: all)")
    parser.add_argument("--output", type=str, default=None,
                        help="Save JSON results to this file")
    parser.add_argument("--no-grafana", action="store_true",
                        help="Skip Grafana (faster startup)")
    parser.add_argument("--no-traffic", action="store_true",
                        help="Skip iperf3 traffic")
    parser.add_argument("--list", action="store_true",
                        help="List available presets and exit")
    args = parser.parse_args()

    if args.list:
        print("Available presets:\n")
        for name, p in PRESETS.items():
            exp_c = {"STABLE": GREEN, "DEGRADED": YELLOW, "CRASH": RED}.get(p["expected"], "")
            print(f"  {name:<15} [{exp_c}{p['expected']}{RESET}]  {p['desc']}")
            print(f"               args: {' '.join(p['args'])}")
        sys.exit(0)

    if args.presets == "all":
        selected = list(PRESETS.keys())
    else:
        selected = [p.strip() for p in args.presets.split(",")]
        for p in selected:
            if p not in PRESETS:
                print(f"Unknown preset: {p}. Use --list to see available presets.")
                sys.exit(1)

    print(f"\n{BOLD}srsRAN Channel Broker — Live Parameter Sweep{RESET}")
    print("=" * 65)
    print(f"  Presets:        {', '.join(selected)}")
    print(f"  Duration:       {args.duration}s per preset")
    print(f"  Attach timeout: {args.attach_timeout}s")
    print(f"  Total presets:  {len(selected)}")
    est = len(selected) * (args.attach_timeout + args.duration + POST_STOP_WAIT + 30)
    print(f"  Estimated time: ~{est // 60}m {est % 60}s (worst case)")
    print("=" * 65)

    # Verify prerequisites
    if not LAUNCH.exists():
        print(f"ERROR: launch script not found: {LAUNCH}")
        sys.exit(1)
    if not STOP.exists():
        print(f"ERROR: stop script not found: {STOP}")
        sys.exit(1)

    all_results = []
    sweep_start = time.time()

    for name in selected:
        preset = PRESETS[name]
        try:
            result = run_preset(
                name, preset, args.duration, args.attach_timeout,
                args.no_grafana, args.no_traffic)
            all_results.append(result)
        except KeyboardInterrupt:
            err("Interrupted — stopping pipeline and saving partial results")
            stop_pipeline()
            break
        except Exception as e:
            err(f"Unexpected error in preset {name}: {e}")
            stop_pipeline()
            all_results.append({
                "preset": name,
                "desc":   preset["desc"],
                "status": "ERROR",
                "reason": str(e),
                "metrics": {},
            })

    sweep_elapsed = time.time() - sweep_start
    print(f"\n  Total sweep time: {sweep_elapsed/60:.1f} minutes")
    print_summary(all_results)

    if args.output:
        out_path = Path(args.output)
        with open(out_path, "w") as f:
            json.dump({
                "sweep_timestamp": datetime.now().isoformat(),
                "duration_per_preset": args.duration,
                "total_elapsed_s": round(sweep_elapsed),
                "results": all_results,
            }, f, indent=2)
        print(f"\n  Results saved to: {out_path}")


if __name__ == "__main__":
    main()
