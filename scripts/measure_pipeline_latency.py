#!/usr/bin/env python3
"""
Pipeline Latency & Overhead Comparison
=======================================
Empirically measures and compares the end-to-end reporting latency of the
jBPF (jrtc) pipeline against the standard srsRAN / Telegraf pipeline for
every overlapping metric.

Three measurements per metric
------------------------------
1. First-sample delay  — seconds from session start until the pipeline
   delivers its first data point for this metric.
2. Reporting interval  — mean / median / p95 of consecutive inter-sample
   gaps (= how stale the data gets between updates).
3. Cross-correlation lag — both series are interpolated onto a 0.25 s grid
   and the lag at peak cross-correlation is found.  A positive lag means
   jBPF *leads* standard (delivers the measurement earlier).

Overhead
---------
For metrics produced by an eBPF hook, the cost per sample is obtained from
the jbpf_perf measurement: invocations × p50_exec_time → CPU %.
MAC-layer hook overhead is bounded by the OFF/ON experiment (<0.6 % of 1
core for all 60 codelets combined) and is noted accordingly.
Standard pipeline overhead is the Telegraf HTTP-poll cycle (once per ~1.68 s
covering all metrics simultaneously); no per-metric gNB computation is added.

Outputs
--------
  docs/comparison/data/pipeline_latency.json  — full numeric results
  (stdout table)                              — human-readable summary
"""

import csv
import json
import sys
import urllib.request
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# ── paths ─────────────────────────────────────────────────────────────
REPO     = Path(__file__).resolve().parent.parent
OUT_JSON = REPO / "docs" / "comparison" / "data" / "pipeline_latency.json"

JBPF_URL = "http://localhost:8086"
JBPF_DB  = "srsran_telemetry"
STD_URL  = "http://localhost:8081"
STD_DB   = "srsran"

# ── metric definitions ─────────────────────────────────────────────────
# Each entry: name, jBPF table, jBPF value field, standard ue-table field,
#             optional transform for jBPF value, generating hook, perf-instrumented flag
METRICS = [
    dict(name="SINR",
         jbpf_table="mac_crc_stats",   jbpf_field="avg_sinr",
         std_field="pusch_snr_db",
         hook="mac_sched_crc_indication",   perf=False),
    dict(name="UL BLER",
         jbpf_table="mac_crc_stats",   jbpf_field="tx_success_rate",
         std_field=None,               # computed from ul_nof_ok/nok below
         hook="mac_sched_crc_indication",   perf=False),
    dict(name="CQI",
         jbpf_table="mac_uci_stats",   jbpf_field="avg_cqi",
         std_field="cqi",
         hook="mac_sched_uci_indication",   perf=False),
    dict(name="TA",
         jbpf_table="mac_uci_stats",   jbpf_field="avg_timing_advance",
         std_field="ta_ns",
         hook="mac_sched_uci_indication",   perf=False),
    dict(name="RI",
         jbpf_table="mac_uci_stats",   jbpf_field="avg_ri",
         std_field="dl_ri",
         hook="mac_sched_uci_indication",   perf=False),
    dict(name="BSR",
         jbpf_table="mac_bsr_stats",   jbpf_field="avg_bytes_per_report",
         std_field="bsr",
         hook="mac_sched_ul_bsr",           perf=False),
    dict(name="DL MCS",
         jbpf_table="fapi_dl_config",  jbpf_field="avg_mcs",
         std_field="dl_mcs",
         hook="fapi_dl_tti_request",        perf=True),
    dict(name="UL MCS",
         jbpf_table="fapi_ul_config",  jbpf_field="avg_mcs",
         std_field="ul_mcs",
         hook="fapi_ul_tti_request",        perf=True),
    dict(name="DL Mbps",
         jbpf_table="ue_dl_throughput", jbpf_field="bitrate_mbps",
         std_field="dl_brate",
         hook="iperf3_reader (not a hook)", perf=False),
    dict(name="UL Mbps",
         jbpf_table="ue_ul_throughput", jbpf_field="bitrate_mbps",
         std_field="ul_brate",
         hook="iperf3_reader (not a hook)", perf=False),
]


# ── DB helpers ────────────────────────────────────────────────────────

def query_influx1(q: str):
    url = (f"{JBPF_URL}/query?db={JBPF_DB}"
           f"&q={urllib.parse.quote(q)}")
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read())
    out = []
    for stmt in data.get("results", []):
        for series in stmt.get("series", []):
            cols = series["columns"]
            tags = series.get("tags", {})
            for row in series["values"]:
                d = dict(zip(cols, row))
                d.update(tags)
                out.append(d)
    return out


def query_influx3(q: str):
    payload = json.dumps({"db": STD_DB, "q": q}).encode()
    req = urllib.request.Request(
        f"{STD_URL}/api/v3/query_sql",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def to_epoch(ts) -> float:
    if isinstance(ts, (int, float)):
        return float(ts)
    ts = str(ts).rstrip("Z")
    if "." in ts:
        base, frac = ts.split(".", 1)
        ts = f"{base}.{frac[:6]}"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt).replace(
                tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse: {ts!r}")


# ── session-start detection ───────────────────────────────────────────

def detect_session_start(rows, gap_threshold=30.0):
    """Return the epoch of the first sample after the largest inter-sample gap."""
    times = sorted(to_epoch(r["time"]) for r in rows)
    if len(times) < 2:
        return times[0] if times else None
    gaps = [(times[i+1] - times[i], times[i+1]) for i in range(len(times)-1)]
    max_gap, session_start = max(gaps, key=lambda x: x[0])
    if max_gap > gap_threshold:
        print(f"  Session gap {max_gap:.0f} s detected; "
              f"session starts at "
              f"{datetime.fromtimestamp(session_start, tz=timezone.utc).strftime('%H:%M:%S')} UTC")
        return session_start
    return times[0]


def trim(rows, session_start):
    return [r for r in rows if to_epoch(r["time"]) >= session_start]


# ── interval statistics ───────────────────────────────────────────────

def interval_stats(times_sorted):
    """Return dict with mean/median/p95/p99 of inter-sample intervals."""
    if len(times_sorted) < 2:
        return {}
    gaps = np.diff(times_sorted)
    return {
        "n":      len(times_sorted),
        "mean":   float(np.mean(gaps)),
        "median": float(np.median(gaps)),
        "p95":    float(np.percentile(gaps, 95)),
        "p99":    float(np.percentile(gaps, 99)),
        "min":    float(np.min(gaps)),
        "max":    float(np.max(gaps)),
    }


# ── cross-correlation lag ─────────────────────────────────────────────

def xcorr_lag(t_a, v_a, t_b, v_b, grid_step=0.25, max_lag_s=5.0):
    """
    Estimate the lag (in seconds) by which series A *leads* series B.
    Positive result → A delivers data earlier than B.

    Both series are interpolated onto a shared grid at `grid_step` spacing,
    zero-meaned, then cross-correlated.  Returns None when either series
    has insufficient variance (constant CQI, RI, etc.).
    """
    if len(t_a) < 4 or len(t_b) < 4:
        return None

    t_start = max(min(t_a), min(t_b))
    t_end   = min(max(t_a), max(t_b))
    if t_end - t_start < 10:
        return None

    grid = np.arange(t_start, t_end, grid_step)
    ya   = np.interp(grid, t_a, v_a)
    yb   = np.interp(grid, t_b, v_b)

    # Reject constant series
    if np.std(ya) < 1e-6 or np.std(yb) < 1e-6:
        return None

    ya -= ya.mean()
    yb -= yb.mean()

    # Full cross-correlation
    cc  = np.correlate(ya, yb, mode="full")
    lags = np.arange(-(len(ya)-1), len(yb)) * grid_step  # seconds
    mask = np.abs(lags) <= max_lag_s
    best = int(np.argmax(cc[mask]))
    lag_s = float(lags[mask][best])
    # Convention: cc[k] = sum_n ya[n] * yb[n - lag].
    # If ya leads yb by D seconds, peak is at lag = -D/step → lag_s < 0.
    # We negate so that the returned value is positive when jBPF leads.
    return -lag_s


# ── jbpf_perf overhead extraction ────────────────────────────────────

def extract_perf_overhead(session_start):
    """
    From jbpf_perf, compute per-hook:
      invocations_per_s, p50_us, p90_us, p99_us, cpu_pct
    Returns dict keyed by hook name.
    """
    rows = query_influx1(
        "SELECT * FROM jbpf_perf ORDER BY time ASC"
    )
    rows = trim(rows, session_start)
    if not rows:
        return {}

    from collections import defaultdict
    by_hook = defaultdict(list)
    for r in rows:
        hook = r.get("hook", "unknown")
        by_hook[hook].append(r)

    session_len = max(to_epoch(r["time"]) for r in rows) - session_start

    result = {}
    for hook, hrs in by_hook.items():
        # "invocations" = count of hook calls in that 1-s window
        total_inv = sum(float(r.get("invocations", 0) or 0) for r in hrs)
        # p50/p90/p99 are stored in nanoseconds
        p50s = [float(r["p50"]) / 1000 for r in hrs if r.get("p50") is not None]
        p90s = [float(r["p90"]) / 1000 for r in hrs if r.get("p90") is not None]
        p99s = [float(r["p99"]) / 1000 for r in hrs if r.get("p99") is not None]
        if not p50s:
            continue
        inv_per_s  = total_inv / session_len if session_len > 0 else 0
        p50_median = float(np.median(p50s))
        # CPU fraction: invocations/s × median_exec_us × 1e-6 × 100 %
        cpu_pct    = inv_per_s * p50_median / 1e6 * 100
        result[hook] = {
            "inv_per_s": round(inv_per_s, 1),
            "p50_us":    round(p50_median, 3),
            "p90_us":    round(float(np.median(p90s)), 3) if p90s else None,
            "p99_us":    round(float(np.median(p99s)), 3) if p99s else None,
            "cpu_pct":   round(cpu_pct, 4),
        }
    return result


# ── delivery latency report (from telemetry_to_influxdb.py latency CSV) ──────

def latency_report(csv_path: str) -> None:
    """
    Analyse the per-message delivery latency CSV produced by telemetry_to_influxdb.py
    (written to /tmp/jbpf_delivery_latency.csv during a live session).

    Each row: schema, latency_ns, recv_monotonic_ns, proto_ts_ns
    latency_ns = time from report_stats hook firing to Python decode
    (CLOCK_MONOTONIC ns difference, valid because both bpf_ktime_get_ns()
    and time.monotonic_ns() use the same CLOCK_MONOTONIC on the same host).
    """
    rows = defaultdict(list)
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            ns = int(row["latency_ns"])
            rows[row["schema"]].append(ns)

    print("=" * 72)
    print("jBPF per-message delivery latency  (hook firing → Python decode)")
    print(f"Source: {csv_path}")
    print("=" * 72)

    all_ns = []
    hdr = f"{'Schema':<35}  {'N':>6}  {'p50 ms':>7}  {'p95 ms':>7}  {'p99 ms':>7}  {'max ms':>7}"
    print(hdr)
    print("-" * len(hdr))

    for schema in sorted(rows):
        arr = np.array(rows[schema])
        all_ns.extend(rows[schema])
        p50 = np.percentile(arr, 50) / 1e6
        p95 = np.percentile(arr, 95) / 1e6
        p99 = np.percentile(arr, 99) / 1e6
        mx  = arr.max() / 1e6
        print(f"{schema:<35}  {len(arr):>6}  {p50:>7.2f}  {p95:>7.2f}  {p99:>7.2f}  {mx:>7.2f}")

    if all_ns:
        arr = np.array(all_ns)
        print("-" * len(hdr))
        print(f"{'ALL (combined)':<35}  {len(arr):>6}  "
              f"{np.percentile(arr,50)/1e6:>7.2f}  "
              f"{np.percentile(arr,95)/1e6:>7.2f}  "
              f"{np.percentile(arr,99)/1e6:>7.2f}  "
              f"{arr.max()/1e6:>7.2f}")

    print()
    print("Interpretation:")
    print("  latency = jrtc IPC + UDP loopback + Python protobuf decode")
    print("  (NOT including the BPF collection window; that is shown by reporting interval)")
    print()
    print("Standard pipeline comparison (srsRAN WebSocket → Telegraf → InfluxDB 3):")
    print("  Telegraf poll interval: ~1.68 s mean (measured)")
    print("  Transmission (HTTP GET + parse + InfluxDB write): ~10-50 ms (architecture estimate)")
    print()


# ── main ──────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pipeline latency & overhead measurement")
    parser.add_argument(
        "--latency-report", metavar="CSV",
        help="Print per-message delivery latency from a telemetry_to_influxdb.py "
             "latency CSV file and exit (file written to /tmp/jbpf_delivery_latency.csv "
             "during a live session)."
    )
    args = parser.parse_args()

    if args.latency_report:
        latency_report(args.latency_report)
        return

    print("=" * 64)
    print("Pipeline latency & overhead measurement")
    print("=" * 64)

    # ── 1. Load standard UE series (used for session detection + all metrics)
    print("\n[1/4] Loading standard ue table …")
    std_ue_all = query_influx3("SELECT * FROM ue ORDER BY time ASC")
    session_start = detect_session_start(std_ue_all)
    std_ue = trim(std_ue_all, session_start)

    # Build standard ul BLER helper arrays
    std_times  = np.array([to_epoch(r["time"]) for r in std_ue])
    std_ul_ok  = np.array([float(r["ul_nof_ok"]) if r.get("ul_nof_ok") is not None else np.nan
                           for r in std_ue])
    std_ul_nok = np.array([float(r["ul_nof_nok"]) if r.get("ul_nof_nok") is not None else np.nan
                           for r in std_ue])
    total_ul   = std_ul_ok + std_ul_nok
    with np.errstate(invalid="ignore", divide="ignore"):
        std_bler   = np.where(total_ul > 0, std_ul_nok / total_ul * 100, np.nan)

    # brate fields need scaling: ue table stores brate in bps → convert to Mbps
    def brate_to_mbps(v):
        return float(v) / 1e6 if v is not None else None

    print(f"  Standard: {len(std_ue)} rows after gap trim")

    # ── 2. Load jbpf_perf overhead data
    print("\n[2/4] Loading jbpf_perf hook overhead …")
    perf = extract_perf_overhead(session_start)
    print(f"  Found perf data for {len(perf)} hooks: {list(perf.keys())}")

    # ── 3. Process each metric
    print("\n[3/4] Computing latency statistics per metric …")
    results = {}

    for m in METRICS:
        name = m["name"]
        print(f"  {name} …")

        # Load jBPF series
        jbpf_rows_all = query_influx1(
            f"SELECT * FROM {m['jbpf_table']} ORDER BY time ASC"
        )
        jbpf_rows = trim(jbpf_rows_all, session_start)

        if not jbpf_rows:
            print(f"    [skip] no jBPF data")
            continue

        # Extract jBPF times and values
        jbpf_t, jbpf_v = [], []
        for r in jbpf_rows:
            t  = to_epoch(r["time"])
            raw = r.get(m["jbpf_field"])
            if raw is None:
                continue
            val = float(raw)
            # UL BLER: convert success-rate → BLER %
            if name == "UL BLER":
                val = 100.0 - val
            # TA: raw value from jBPF is in T_c units → convert to ns
            if name == "TA":
                val = val * (1e9 / (480_000 * 4_096))
            jbpf_t.append(t)
            jbpf_v.append(val)

        if not jbpf_t:
            print(f"    [skip] no valid jBPF values")
            continue

        jbpf_t = np.array(jbpf_t)
        jbpf_v = np.array(jbpf_v)

        # Extract standard times and values
        std_t, std_v = [], []
        for i, r in enumerate(std_ue):
            t = std_times[i]
            if m["name"] == "UL BLER":
                val = std_bler[i]
                if np.isnan(val):
                    continue
            elif m["name"] in ("DL Mbps", "UL Mbps"):
                field = "dl_brate" if m["name"] == "DL Mbps" else "ul_brate"
                raw = r.get(field)
                if raw is None:
                    continue
                val = brate_to_mbps(raw)
            else:
                raw = r.get(m["std_field"])
                if raw is None:
                    continue
                val = float(raw)
            std_t.append(t)
            std_v.append(val)

        if not std_t:
            print(f"    [skip] no valid standard values")
            continue

        std_t = np.array(std_t)
        std_v = np.array(std_v)

        # ── Reporting interval stats
        jbpf_istat = interval_stats(sorted(jbpf_t))
        std_istat  = interval_stats(sorted(std_t))

        # ── First-sample delay from session start
        jbpf_first_delay = float(np.min(jbpf_t) - session_start)
        std_first_delay  = float(np.min(std_t)  - session_start)

        # ── Cross-correlation lag (jBPF leads standard by X seconds)
        # Sort both arrays by time first
        order_j = np.argsort(jbpf_t)
        order_s = np.argsort(std_t)
        lag = xcorr_lag(jbpf_t[order_j], jbpf_v[order_j],
                        std_t[order_s],  std_v[order_s])

        # ── jBPF hook overhead from perf (if available)
        hook_overhead = None
        if m["perf"] and m["hook"] in perf:
            hook_overhead = perf[m["hook"]]

        results[name] = {
            "jbpf_interval":    jbpf_istat,
            "std_interval":     std_istat,
            "jbpf_first_delay": round(jbpf_first_delay, 2),
            "std_first_delay":  round(std_first_delay, 2),
            "xcorr_lag_s":      round(lag, 3) if lag is not None else None,
            "hook":             m["hook"],
            "hook_perf":        hook_overhead,
        }

        lag_str = f"{lag:+.2f} s" if lag is not None else "n/a (constant)"
        print(f"    jBPF interval: {jbpf_istat.get('mean', 0):.3f} s mean  "
              f"| std interval: {std_istat.get('mean', 0):.3f} s mean  "
              f"| xcorr lag: {lag_str}")

    # ── 4. Print summary table
    print("\n[4/4] Summary")
    print("=" * 64)

    hdr = (f"{'Metric':<10}  {'jBPF mean':>10}  {'Std mean':>10}  "
           f"{'jBPF p95':>9}  {'Std p95':>9}  {'xcorr lag':>10}  "
           f"{'jBPF 1st':>9}  {'Std 1st':>9}")
    print(hdr)
    print("-" * len(hdr))

    for name, r in results.items():
        ji = r["jbpf_interval"]
        si = r["std_interval"]
        lag = r["xcorr_lag_s"]
        lag_str = f"{lag:+.2f} s" if lag is not None else "  n/a    "
        print(
            f"{name:<10}  "
            f"{ji.get('mean', 0):>10.3f}  "
            f"{si.get('mean', 0):>10.3f}  "
            f"{ji.get('p95', 0):>9.2f}  "
            f"{si.get('p95', 0):>9.2f}  "
            f"{lag_str:>10}  "
            f"{r['jbpf_first_delay']:>9.1f}  "
            f"{r['std_first_delay']:>9.1f}"
        )

    print()

    # ── Hook overhead summary
    if perf:
        print("jBPF hook overhead (perf-instrumented hooks)")
        print(f"  {'Hook':<35}  {'Inv/s':>7}  {'p50 µs':>7}  {'p99 µs':>7}  {'CPU %':>7}")
        print("  " + "-" * 70)
        for hook, h in sorted(perf.items(), key=lambda x: -x[1]["cpu_pct"]):
            print(f"  {hook:<35}  {h['inv_per_s']:>7.0f}  "
                  f"{h['p50_us']:>7.3f}  "
                  f"{(h['p99_us'] or 0):>7.3f}  "
                  f"{h['cpu_pct']:>7.4f}")
        total_perf_cpu = sum(h["cpu_pct"] for h in perf.values())
        print(f"  {'TOTAL (perf-instrumented)':<35}  {'':>7}  {'':>7}  {'':>7}  "
              f"{total_perf_cpu:>7.4f}")

    # ── Save JSON
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump({
            "session_start_utc": datetime.fromtimestamp(
                session_start, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "metrics": results,
            "perf_hooks": perf,
        }, f, indent=2)
    print(f"\nResults saved → {OUT_JSON}")


if __name__ == "__main__":
    main()
