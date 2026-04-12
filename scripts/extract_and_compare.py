#!/usr/bin/env python3
"""
jBPF vs srsRAN Standard Telemetry — Data Extraction, Comparison & Plotting
===========================================================================
Extracts all metrics from both telemetry sources:
  - jBPF eBPF codelets  → InfluxDB 1.x on :8086
  - srsRAN standard      → InfluxDB 3    on :8081

Produces:
  • CSV exports for every measurement
  • Comparison plots for all overlapping metrics (01–10)
  • Summary / correlation plots (11–12)
  • jBPF-exclusive plots (13–18)
  • Standard-exclusive plots (19–26)
  • statistics.json with per-metric summary stats

Plot index
----------
Comparison (jBPF vs Standard):
  01  SINR / SNR
  02  CQI
  03  DL MCS
  04  UL MCS
  05  DL Throughput
  06  UL Throughput
  07  UL BLER  (jBPF UL CRC  vs  std ul_nof_ok/nok — same direction)
  08  BSR
  09  Timing Advance
  10  Rank Indicator (RI)
Summary:
  11  Mean-value bar chart
  12  Correlation scatter grid
jBPF-exclusive:
  13  Hook latency (p50 per hook, all 22 hooks)
  14  Ping RTT
  15  PRB allocation  (DL + UL avg/min/max)
  16  HARQ retransmissions  (DL + UL retx_count, max_retx)
  17  DL iperf3 packet quality  (jitter, loss %)
  18  Per-slot SINR range  (fapi_crc_stats snr_min/max, ×0.1 dB)
Standard-exclusive:
  19  PUCCH SNR vs PUSCH SNR
  20  TA channels  (pucch_ta_ns / pusch_ta_ns / combined ta_ns)
  21  DL buffer status  (dl_bs)
  22  HARQ processing delays  (avg_crc / pucch_harq / pusch_harq delay)
  23  Cell scheduling latency + histogram
  24  PUCCH RB usage
  25  DU High thread latency
  26  UL + DL HARQ BLER from standard  (direction-asymmetry context)
"""

import json
import csv
import os
import sys
import argparse
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# ── Output directories ────────────────────────────────────────────────
OUT_DIR  = Path(__file__).resolve().parent.parent / "docs" / "comparison"
PLOT_DIR = OUT_DIR / "figures"
CSV_DIR  = OUT_DIR / "data"
for d in (OUT_DIR, PLOT_DIR, CSV_DIR):
    d.mkdir(parents=True, exist_ok=True)

JBPF_URL = "http://localhost:8086"
JBPF_DB  = "srsran_telemetry"
STD_URL  = "http://localhost:8081"
STD_DB   = "srsran"

# NR timing-advance constant: T_c = 1/(480 000 × 4096) s  →  T_c in ns
_TC_NS = 1e9 / (480_000 * 4_096)   # ≈ 0.508 626 ns per T_c unit

# fapi_crc_stats SNR is in units of 0.1 dB
_FAPI_SNR_SCALE = 0.1

# Optional time window (set by CLI args, None = full history)
TIME_START = None
TIME_END   = None


# ─────────────────────────── helpers ──────────────────────────────────

def _time_clause_influx1():
    parts = []
    if TIME_START:
        parts.append(f"time >= '{TIME_START}'")
    if TIME_END:
        parts.append(f"time <= '{TIME_END}'")
    return " AND ".join(parts)


def _time_clause_sql():
    parts = []
    if TIME_START:
        parts.append(f"time >= '{TIME_START}'")
    if TIME_END:
        parts.append(f"time <= '{TIME_END}'")
    return " AND ".join(parts)


def _inject_where(q, clause):
    """Inject WHERE / AND clause into a query that may already have WHERE."""
    if not clause:
        return q
    q_upper = q.upper()
    if "WHERE" in q_upper:
        idx = q_upper.index("WHERE") + len("WHERE")
        return q[:idx] + " " + clause + " AND" + q[idx:]
    for kw in ("ORDER BY", "GROUP BY", "LIMIT"):
        if kw in q_upper:
            idx = q_upper.index(kw)
            return q[:idx] + "WHERE " + clause + " " + q[idx:]
    return q + " WHERE " + clause


def query_influx1(q: str):
    """Query InfluxDB 1.x → list of dicts."""
    q = _inject_where(q, _time_clause_influx1())
    url = f"{JBPF_URL}/query?db={JBPF_DB}&q={urllib.parse.quote(q)}"
    with urllib.request.urlopen(url, timeout=10) as r:
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
    """Query InfluxDB 3 (SQL) → list of dicts."""
    q = _inject_where(q, _time_clause_sql())
    payload = json.dumps({"db": STD_DB, "q": q}).encode()
    req = urllib.request.Request(
        f"{STD_URL}/api/v3/query_sql",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def to_epoch(ts_str: str) -> float:
    """Convert ISO timestamp string to Unix epoch seconds."""
    ts_str = ts_str.rstrip("Z")
    if "." in ts_str:
        base, frac = ts_str.split(".", 1)
        ts_str = f"{base}.{frac[:6]}"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts_str, fmt).replace(
                tzinfo=timezone.utc
            ).timestamp()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {ts_str!r}")


def save_csv(rows, filename):
    if not rows:
        return
    # Collect union of all keys (rows may have different sparse fields)
    all_keys = list(dict.fromkeys(k for r in rows for k in r.keys()))
    path = CSV_DIR / filename
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore",
                           restval="")
        w.writeheader()
        w.writerows(rows)
    print(f"  Saved {len(rows)} rows → {path.name}")


# ───────────────────────── jBPF extraction ──────────────────────────

def extract_jbpf():
    """Extract all jBPF measurements from InfluxDB 1.x."""
    print("[1/4] Extracting jBPF telemetry from InfluxDB 1.x …")
    ds = {}

    measurements = {
        "crc":      "SELECT * FROM mac_crc_stats   ORDER BY time ASC",
        "uci":      "SELECT * FROM mac_uci_stats   ORDER BY time ASC",
        "harq":     "SELECT * FROM mac_harq_stats  ORDER BY time ASC",
        "bsr":      "SELECT * FROM mac_bsr_stats   ORDER BY time ASC",
        "fapi_dl":  "SELECT * FROM fapi_dl_config  ORDER BY time ASC",
        "fapi_ul":  "SELECT * FROM fapi_ul_config  ORDER BY time ASC",
        "fapi_crc": "SELECT * FROM fapi_crc_stats  ORDER BY time ASC",
        "tp_dl":    "SELECT * FROM ue_dl_throughput ORDER BY time ASC",
        "tp_ul":    "SELECT * FROM ue_ul_throughput ORDER BY time ASC",
        "rtt":      "SELECT * FROM ue_rtt           ORDER BY time ASC",
        "perf":     "SELECT * FROM jbpf_perf        ORDER BY time ASC",
    }
    csv_names = {
        "crc": "jbpf_crc_stats.csv", "uci": "jbpf_uci_stats.csv",
        "harq": "jbpf_harq_stats.csv", "bsr": "jbpf_bsr_stats.csv",
        "fapi_dl": "jbpf_fapi_dl.csv", "fapi_ul": "jbpf_fapi_ul.csv",
        "fapi_crc": "jbpf_fapi_crc.csv",
        "tp_dl": "jbpf_throughput_dl.csv", "tp_ul": "jbpf_throughput_ul.csv",
        "rtt": "jbpf_rtt.csv", "perf": "jbpf_perf.csv",
    }
    for key, q in measurements.items():
        rows = query_influx1(q)
        ds[key] = rows
        save_csv(rows, csv_names[key])

    print(f"  jBPF: {sum(len(v) for v in ds.values())} total rows across "
          f"{len(ds)} measurements")
    return ds


# ─────────────────────── standard extraction ────────────────────────

def extract_standard():
    """Extract ALL srsRAN standard metrics from InfluxDB 3 (all tables)."""
    print("[2/4] Extracting srsRAN standard metrics from InfluxDB 3 …")
    result = {}

    # UE metrics — all fields
    ue = query_influx3("SELECT * FROM ue ORDER BY time ASC")
    result["ue"] = ue
    save_csv(ue, "standard_ue_metrics.csv")

    # Cell metrics
    cell = query_influx3("SELECT * FROM cell ORDER BY time ASC")
    result["cell"] = cell
    save_csv(cell, "standard_cell_metrics.csv")

    # DU High thread metrics
    du = query_influx3("SELECT * FROM du ORDER BY time ASC")
    result["du"] = du
    save_csv(du, "standard_du_metrics.csv")

    # Event list
    events = query_influx3("SELECT * FROM event_list ORDER BY time ASC")
    result["events"] = events
    save_csv(events, "standard_events.csv")

    print(f"  Standard: ue={len(ue)}, cell={len(cell)}, "
          f"du={len(du)}, events={len(events)} rows")
    return result


# ─────────────────────── time-aligned merge ─────────────────────────

def build_aligned_series(jbpf, std_ue):
    """
    Build time-aligned series for each overlapping metric pair.
    jBPF reports every ~2 s, standard every ~1 s.
    Alignment: nearest-neighbour within ±1 s.
    """
    print("[3/4] Aligning time series …")

    std_times = np.array([to_epoch(r["time"]) for r in std_ue])

    def nearest(t, field):
        diffs = np.abs(std_times - t)
        idx = np.argmin(diffs)
        return std_ue[idx].get(field) if diffs[idx] <= 1.0 else None

    aligned = {}

    # Helper: build a simple paired series from a jBPF measurement
    def pair(jbpf_rows, jbpf_field, std_field, key, csv_name,
             jbpf_transform=None, std_transform=None):
        series = []
        for r in jbpf_rows:
            t = to_epoch(r["time"])
            jv = r.get(jbpf_field)
            sv = nearest(t, std_field)
            if jbpf_transform and jv is not None:
                jv = jbpf_transform(float(jv))
            if std_transform and sv is not None:
                sv = std_transform(float(sv))
            series.append({"time": r["time"], "epoch": t,
                           f"jbpf_{key}": jv, f"std_{key}": sv})
        aligned[key] = series
        save_csv(series, csv_name)

    # 1. SINR / SNR
    pair(jbpf["crc"], "avg_sinr", "pusch_snr_db",
         "sinr", "aligned_sinr_snr.csv")

    # 2. CQI
    pair(jbpf["uci"], "avg_cqi", "cqi",
         "cqi", "aligned_cqi.csv")

    # 3. DL MCS
    pair(jbpf["fapi_dl"], "avg_mcs", "dl_mcs",
         "dl_mcs", "aligned_dl_mcs.csv")

    # 4. UL MCS
    pair(jbpf["fapi_ul"], "avg_mcs", "ul_mcs",
         "ul_mcs", "aligned_ul_mcs.csv")

    # 5. DL Throughput  (jBPF=iperf3 Mbps, std=MAC bps → convert to Mbps)
    series = []
    for r in jbpf.get("tp_dl", []):
        t = to_epoch(r["time"])
        sv = nearest(t, "dl_brate")
        series.append({"time": r["time"], "epoch": t,
                        "jbpf_dl_mbps": r.get("bitrate_mbps"),
                        "std_dl_mbps": float(sv)/1e6 if sv is not None else None})
    aligned["dl_tp"] = series
    save_csv(series, "aligned_dl_bitrate.csv")

    # 6. UL Throughput
    series = []
    for r in jbpf.get("tp_ul", []):
        t = to_epoch(r["time"])
        sv = nearest(t, "ul_brate")
        series.append({"time": r["time"], "epoch": t,
                        "jbpf_ul_mbps": r.get("bitrate_mbps"),
                        "std_ul_mbps": float(sv)/1e6 if sv is not None else None})
    aligned["ul_tp"] = series
    save_csv(series, "aligned_ul_bitrate.csv")

    # 7. UL BLER — jBPF UL CRC failure  vs  std ul_nof_ok/nok (SAME direction)
    #    Note: std dl_nof_ok/nok is DL HARQ (different direction — plotted in §26)
    series = []
    for r in jbpf.get("crc", []):
        t = to_epoch(r["time"])
        ul_ok  = nearest(t, "ul_nof_ok")
        ul_nok = nearest(t, "ul_nof_nok")
        std_ul_bler = None
        if ul_ok is not None and ul_nok is not None:
            total = float(ul_ok) + float(ul_nok)
            std_ul_bler = float(ul_nok) / total * 100 if total > 0 else 0.0
        tx_sr = r.get("tx_success_rate")
        jbpf_bler = 100.0 - float(tx_sr) if tx_sr is not None else None
        series.append({"time": r["time"], "epoch": t,
                        "jbpf_ul_bler_pct": jbpf_bler,
                        "std_ul_bler_pct": std_ul_bler})
    aligned["ul_bler"] = series
    save_csv(series, "aligned_ul_bler.csv")

    # 8. BSR — use avg_bytes_per_report (per-CE average, comparable to std snapshot)
    pair(jbpf["bsr"], "avg_bytes_per_report", "bsr",
         "bsr", "aligned_bsr.csv")

    # 9. Timing Advance — convert jBPF raw N_TA index → nanoseconds
    series = []
    for r in jbpf.get("uci", []):
        t = to_epoch(r["time"])
        raw_ta = r.get("avg_timing_advance")
        jv = float(raw_ta) * _TC_NS if raw_ta is not None else None
        sv = nearest(t, "ta_ns")
        series.append({"time": r["time"], "epoch": t,
                        "jbpf_ta_ns": jv, "std_ta_ns": sv})
    aligned["ta"] = series
    save_csv(series, "aligned_ta.csv")

    # 10. Rank Indicator — jBPF avg_ri  vs  std dl_ri
    pair(jbpf["uci"], "avg_ri", "dl_ri",
         "ri", "aligned_ri.csv")

    return aligned


# ─────────────────────────── plotting ────────────────────────────────

def _setup_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    plt.rcParams.update({
        "figure.figsize": (12, 5),
        "font.size": 11,
        "axes.grid": True,
        "grid.alpha": 0.3,
    })
    return plt, mdates


def epoch_to_dt(ep):
    return datetime.fromtimestamp(ep, tz=timezone.utc)


def _extract_xy(series, key):
    """Return (datetime_list, float_list) dropping None entries."""
    ts, vs = [], []
    for r in series:
        v = r.get(key)
        if v is not None:
            ts.append(epoch_to_dt(r["epoch"]))
            vs.append(float(v))
    return ts, vs


def plot_comparison(series, jbpf_key, std_key, title, ylabel, fname,
                    jbpf_label="jBPF (eBPF codelets)",
                    std_label="Standard (srsRAN)"):
    """Two-trace time-series comparison plot."""
    try:
        plt, mdates = _setup_matplotlib()
    except ImportError:
        return
    fig, ax = plt.subplots()
    jt, jv = _extract_xy(series, jbpf_key)
    st, sv = _extract_xy(series, std_key)
    if jt:
        ax.plot(jt, jv, "o-", ms=2.5, lw=1.2, color="#1f77b4",
                label=jbpf_label, alpha=0.85)
    if st:
        ax.plot(st, sv, "s-", ms=2.5, lw=1.2, color="#ff7f0e",
                label=std_label, alpha=0.85)
    ax.set_title(title, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Time (UTC)")
    ax.legend(loc="best")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / fname, dpi=150)
    plt.close(fig)
    print(f"  Plot → {fname}")


def plot_single(times, values, title, ylabel, fname, label="", color="#2ca02c"):
    """Single-trace time-series plot."""
    try:
        plt, mdates = _setup_matplotlib()
    except ImportError:
        return
    fig, ax = plt.subplots()
    ax.plot(times, values, "o-", ms=2, lw=1, color=color,
            label=label, alpha=0.85)
    ax.set_title(title, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Time (UTC)")
    if label:
        ax.legend(loc="best")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / fname, dpi=150)
    plt.close(fig)
    print(f"  Plot → {fname}")


def plot_multi(traces, title, ylabel, fname, colors=None):
    """
    Multi-trace time-series plot.
    traces: list of (label, times_list, values_list)
    """
    try:
        plt, mdates = _setup_matplotlib()
    except ImportError:
        return
    default_colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
                      "#9467bd", "#8c564b"]
    fig, ax = plt.subplots()
    for i, (label, ts, vs) in enumerate(traces):
        c = (colors[i] if colors and i < len(colors)
             else default_colors[i % len(default_colors)])
        if ts:
            ax.plot(ts, vs, "o-", ms=2, lw=1.2, color=c,
                    label=label, alpha=0.85)
    ax.set_title(title, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Time (UTC)")
    ax.legend(loc="best", fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / fname, dpi=150)
    plt.close(fig)
    print(f"  Plot → {fname}")


def make_plots(aligned, jbpf, standard):
    print("[4/4] Generating plots …")
    try:
        _setup_matplotlib()
    except ImportError:
        print("  matplotlib not installed — skipping plots")
        return

    std_ue   = standard.get("ue",   [])
    std_cell = standard.get("cell", [])
    std_du   = standard.get("du",   [])

    # ── SECTION 1: Comparison (jBPF vs Standard) ─────────────────────

    # 01 SINR / SNR
    if "sinr" in aligned:
        plot_comparison(aligned["sinr"], "jbpf_sinr", "std_sinr",
                        "SINR / SNR Comparison (jBPF UL CRC  vs  Standard PUSCH)",
                        "dB", "01_sinr_snr_comparison.png",
                        "jBPF avg_sinr (mac_crc_stats)",
                        "Standard pusch_snr_db")

    # 02 CQI
    if "cqi" in aligned:
        plot_comparison(aligned["cqi"], "jbpf_cqi", "std_cqi",
                        "CQI Comparison",
                        "CQI Index", "02_cqi_comparison.png")

    # 03 DL MCS
    if "dl_mcs" in aligned:
        plot_comparison(aligned["dl_mcs"], "jbpf_dl_mcs", "std_dl_mcs",
                        "DL MCS Comparison (jBPF FAPI  vs  Standard)",
                        "MCS Index", "03_dl_mcs_comparison.png",
                        "jBPF avg_mcs (fapi_dl_config)", "Standard dl_mcs")

    # 04 UL MCS
    if "ul_mcs" in aligned:
        plot_comparison(aligned["ul_mcs"], "jbpf_ul_mcs", "std_ul_mcs",
                        "UL MCS Comparison (jBPF FAPI  vs  Standard)",
                        "MCS Index", "04_ul_mcs_comparison.png",
                        "jBPF avg_mcs (fapi_ul_config)", "Standard ul_mcs")

    # 05 DL Throughput
    if "dl_tp" in aligned:
        plot_comparison(aligned["dl_tp"], "jbpf_dl_mbps", "std_dl_mbps",
                        "DL Throughput Comparison\n"
                        "(jBPF iperf3 application layer  vs  Standard MAC layer)",
                        "Mbps", "05_dl_throughput_comparison.png",
                        "jBPF iperf3 DL (app layer)", "Standard dl_brate (MAC layer)")

    # 06 UL Throughput
    if "ul_tp" in aligned:
        plot_comparison(aligned["ul_tp"], "jbpf_ul_mbps", "std_ul_mbps",
                        "UL Throughput Comparison\n"
                        "(jBPF iperf3 application layer  vs  Standard MAC layer)",
                        "Mbps", "06_ul_throughput_comparison.png",
                        "jBPF iperf3 UL (app layer)", "Standard ul_brate (MAC layer)")

    # 07 UL BLER — same link direction
    if "ul_bler" in aligned:
        plot_comparison(aligned["ul_bler"], "jbpf_ul_bler_pct", "std_ul_bler_pct",
                        "UL BLER Comparison — Same Direction\n"
                        "(jBPF UL CRC failure  vs  Standard UL HARQ NACK rate)",
                        "BLER (%)", "07_ul_bler_comparison.png",
                        "jBPF UL CRC BLER (mac_crc_stats)",
                        "Standard UL HARQ BLER (ul_nof_nok / total)")

    # 08 BSR
    if "bsr" in aligned:
        plot_comparison(aligned["bsr"], "jbpf_bsr", "std_bsr",
                        "Buffer Status Report Comparison",
                        "Bytes", "08_bsr_comparison.png",
                        "jBPF avg_bytes_per_report (mac_bsr_stats)",
                        "Standard bsr (instantaneous snapshot)")

    # 09 Timing Advance
    if "ta" in aligned:
        plot_comparison(aligned["ta"], "jbpf_ta_ns", "std_ta_ns",
                        "Timing Advance Comparison (after N_TA × T_c conversion)",
                        "ns", "09_ta_comparison.png",
                        "jBPF N_TA × T_c  (mac_uci_stats)", "Standard ta_ns")

    # 10 Rank Indicator
    if "ri" in aligned:
        plot_comparison(aligned["ri"], "jbpf_ri", "std_ri",
                        "Rank Indicator (RI) Comparison",
                        "RI (MIMO layers)", "10_ri_comparison.png",
                        "jBPF avg_ri (mac_uci_stats)", "Standard dl_ri")

    # ── SECTION 2: Summary ───────────────────────────────────────────

    # 11 Summary bar chart
    stats = compute_statistics(aligned)
    if stats:
        _plot_summary_bar(stats)

    # 12 Correlation scatter grid
    _plot_correlation_scatter(aligned)

    # ── SECTION 3: jBPF-exclusive ────────────────────────────────────

    # 13 Hook latency
    _plot_hook_latency(jbpf.get("perf", []))

    # 14 RTT
    rtt = jbpf.get("rtt", [])
    if rtt:
        ts = [epoch_to_dt(to_epoch(r["time"])) for r in rtt if r.get("rtt_ms")]
        vs = [float(r["rtt_ms"]) for r in rtt if r.get("rtt_ms")]
        if ts:
            plot_single(ts, vs, "Ping RTT — jBPF Exclusive",
                        "RTT (ms)", "14_jbpf_rtt.png",
                        color="#2ca02c")

    # 15 PRB allocation (DL + UL avg, min, max)
    _plot_prb_allocation(jbpf)

    # 16 HARQ retransmissions
    _plot_harq_retx(jbpf)

    # 17 DL iperf3 packet quality
    _plot_iperf_quality(jbpf)

    # 18 Per-slot SINR range (fapi_crc_stats snr_min / snr_max)
    _plot_sinr_range(jbpf)

    # ── SECTION 4: Standard-exclusive ───────────────────────────────

    # 19 PUCCH SNR vs PUSCH SNR
    _plot_pucch_pusch_snr(std_ue)

    # 20 TA channels
    _plot_ta_channels(std_ue)

    # 21 DL buffer status
    _plot_dl_bs(std_ue)

    # 22 HARQ processing delays
    _plot_harq_delays(std_ue)

    # 23 Cell scheduling latency + histogram
    _plot_scheduling_latency(std_cell)

    # 24 PUCCH RB usage
    _plot_pucch_rb_usage(std_cell)

    # 25 DU High thread latency
    _plot_du_latency(std_du)

    # 26 Both BLER directions from standard
    _plot_std_bler_directions(std_ue)


# ── Plot helpers ──────────────────────────────────────────────────────

def _plot_summary_bar(stats):
    try:
        plt, _ = _setup_matplotlib()
    except ImportError:
        return
    # Only include metrics where both systems measure the same quantity
    # (exclude throughput ratio and BLER which have structural differences)
    bar_metrics = {k: v for k, v in stats.items()
                   if k not in ("DL Mbps", "UL Mbps")}
    metrics = list(bar_metrics.keys())
    jbpf_means = [bar_metrics[m]["jbpf_mean"] for m in metrics]
    std_means  = [bar_metrics[m]["std_mean"]  for m in metrics]
    fig, ax = plt.subplots(figsize=(14, 6))
    x = np.arange(len(metrics))
    w = 0.35
    ax.bar(x - w/2, jbpf_means, w, label="jBPF", color="#1f77b4", alpha=0.85)
    ax.bar(x + w/2, std_means,  w, label="Standard", color="#ff7f0e", alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics, rotation=30, ha="right")
    ax.set_title("Mean Value Comparison — jBPF vs Standard Telemetry",
                 fontweight="bold")
    ax.set_ylabel("Mean Value (metric-dependent units)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "11_summary_bar_chart.png", dpi=150)
    plt.close(fig)
    print("  Plot → 11_summary_bar_chart.png")


def _plot_correlation_scatter(aligned):
    try:
        plt, _ = _setup_matplotlib()
    except ImportError:
        return
    pairs = [
        ("sinr",   "jbpf_sinr",       "std_sinr",       "SINR (dB)",       "dB"),
        ("dl_mcs", "jbpf_dl_mcs",     "std_dl_mcs",     "DL MCS",          "index"),
        ("ul_mcs", "jbpf_ul_mcs",     "std_ul_mcs",     "UL MCS",          "index"),
        ("ul_bler","jbpf_ul_bler_pct","std_ul_bler_pct","UL BLER",         "%"),
        ("bsr",    "jbpf_bsr",        "std_bsr",        "BSR",             "bytes"),
        ("ta",     "jbpf_ta_ns",      "std_ta_ns",      "TA",              "ns"),
        ("ri",     "jbpf_ri",         "std_ri",         "RI",              "layers"),
    ]
    fig, axes = plt.subplots(1, len(pairs), figsize=(24, 4))
    for i, (key, jk, sk, title, unit) in enumerate(pairs):
        ax = axes[i]
        series = aligned.get(key, [])
        jv = [float(r[jk]) for r in series
              if r.get(jk) is not None and r.get(sk) is not None]
        sv = [float(r[sk]) for r in series
              if r.get(jk) is not None and r.get(sk) is not None]
        if jv:
            ax.scatter(jv, sv, s=12, alpha=0.5, color="#1f77b4")
            lo = min(min(jv), min(sv))
            hi = max(max(jv), max(sv))
            ax.plot([lo, hi], [lo, hi], "k--", lw=0.8, alpha=0.5)
            if len(jv) > 2:
                r_val = np.corrcoef(jv, sv)[0, 1]
                ax.text(0.05, 0.95, f"r = {r_val:.3f}",
                        transform=ax.transAxes, fontsize=9,
                        va="top",
                        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))
        ax.set_xlabel(f"jBPF ({unit})")
        ax.set_ylabel(f"Standard ({unit})")
        ax.set_title(title, fontsize=10)
    fig.suptitle("Correlation: jBPF vs Standard Telemetry",
                 fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "12_correlation_scatter.png",
                dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  Plot → 12_correlation_scatter.png")


def _plot_hook_latency(perf):
    if not perf:
        return
    try:
        plt, mdates = _setup_matplotlib()
    except ImportError:
        return
    hooks = {}
    for r in perf:
        h = r.get("hook")
        if h and r.get("p50"):
            hooks.setdefault(h, []).append(
                (epoch_to_dt(to_epoch(r["time"])), float(r["p50"]) / 1000)
            )
    if not hooks:
        return
    fig, ax = plt.subplots(figsize=(14, 6))
    for hook, pts in sorted(hooks.items()):
        ts, vs = zip(*pts)
        ax.plot(ts, vs, "o-", ms=2, lw=1, label=hook, alpha=0.75)
    ax.set_title("jBPF Hook Latency p50 — jBPF Exclusive", fontweight="bold")
    ax.set_ylabel("Latency (µs)")
    ax.set_xlabel("Time (UTC)")
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "13_jbpf_hook_latency.png", dpi=150)
    plt.close(fig)
    print("  Plot → 13_jbpf_hook_latency.png")


def _plot_prb_allocation(jbpf):
    try:
        plt, mdates = _setup_matplotlib()
    except ImportError:
        return
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, key, direction, color in [
        (axes[0], "fapi_dl", "DL", "#1f77b4"),
        (axes[1], "fapi_ul", "UL", "#ff7f0e"),
    ]:
        rows = jbpf.get(key, [])
        if not rows:
            continue
        times = [epoch_to_dt(to_epoch(r["time"])) for r in rows]
        avg_prb = [float(r["avg_prb"]) for r in rows if r.get("avg_prb") is not None]
        min_prb = [float(r["min_prb"]) for r in rows if r.get("min_prb") is not None]
        max_prb = [float(r["max_prb"]) for r in rows if r.get("max_prb") is not None]
        t_avg = [epoch_to_dt(to_epoch(r["time"])) for r in rows if r.get("avg_prb") is not None]
        if avg_prb:
            ax.plot(t_avg, avg_prb, lw=1.2, color=color, label="avg PRB")
            ax.fill_between(t_avg, min_prb, max_prb,
                            alpha=0.2, color=color, label="min–max range")
        ax.set_title(f"{direction} PRB Allocation — jBPF Exclusive", fontweight="bold")
        ax.set_ylabel("PRBs")
        ax.set_xlabel("Time (UTC)")
        ax.legend(fontsize=9)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        fig.autofmt_xdate()
    fig.suptitle("Physical Resource Block Allocation (jBPF fapi_dl/ul_config)",
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "15_jbpf_prb_allocation.png", dpi=150)
    plt.close(fig)
    print("  Plot → 15_jbpf_prb_allocation.png")


def _plot_harq_retx(jbpf):
    """HARQ retransmission count per 2-s window, DL and UL streams."""
    try:
        plt, mdates = _setup_matplotlib()
    except ImportError:
        return
    harq_rows = jbpf.get("harq", [])
    if not harq_rows:
        return

    # Identify DL stream (higher avg_mcs ~25) and UL stream (lower avg_mcs ~19)
    stream_mcs = {}
    for r in harq_rows:
        sid = r.get("stream_id")
        mcs = r.get("avg_mcs")
        if sid and mcs is not None:
            stream_mcs.setdefault(sid, []).append(float(mcs))
    if not stream_mcs:
        return
    dl_stream = max(stream_mcs, key=lambda s: np.mean(stream_mcs[s]))
    ul_stream = min(stream_mcs, key=lambda s: np.mean(stream_mcs[s]))

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    for ax, sid, label, color in [
        (axes[0], dl_stream, "DL", "#1f77b4"),
        (axes[1], ul_stream, "UL", "#ff7f0e"),
    ]:
        rows = [r for r in harq_rows if r.get("stream_id") == sid]
        ts = [epoch_to_dt(to_epoch(r["time"])) for r in rows]
        retx = [float(r["retx_count"]) for r in rows if r.get("retx_count") is not None]
        max_r = [float(r["max_retx"]) for r in rows if r.get("max_retx") is not None]
        t_r = [epoch_to_dt(to_epoch(r["time"])) for r in rows if r.get("retx_count") is not None]
        if retx:
            ax.bar([t for t in t_r], retx, width=0.0015,
                   color=color, alpha=0.6, label="retx_count (window)")
        if max_r:
            ax2 = ax.twinx()
            ax2.plot(t_r, max_r, "s-", ms=3, lw=1, color="gray",
                     label="max_retx", alpha=0.7)
            ax2.set_ylabel("max retx per TB", color="gray")
        ax.set_title(f"{label} HARQ Retransmissions — jBPF Exclusive",
                     fontweight="bold")
        ax.set_ylabel("retx_count (TBs retransmitted in 2 s window)")
        ax.legend(loc="upper left", fontsize=9)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    axes[-1].set_xlabel("Time (UTC)")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "16_jbpf_harq_retx.png", dpi=150)
    plt.close(fig)
    print("  Plot → 16_jbpf_harq_retx.png")


def _plot_iperf_quality(jbpf):
    """DL iperf3 jitter and packet loss — jBPF exclusive."""
    try:
        plt, mdates = _setup_matplotlib()
    except ImportError:
        return
    rows = [r for r in jbpf.get("tp_dl", []) if r.get("jitter_ms") is not None]
    if not rows:
        return
    ts = [epoch_to_dt(to_epoch(r["time"])) for r in rows]
    jitter = [float(r["jitter_ms"]) for r in rows]
    loss   = [float(r.get("loss_pct") or 0) for r in rows]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    ax1.plot(ts, jitter, "o-", ms=2, lw=1.2, color="#1f77b4", alpha=0.85)
    ax1.set_title("DL iperf3 Jitter — jBPF Exclusive", fontweight="bold")
    ax1.set_ylabel("Jitter (ms)")
    ax2.plot(ts, loss, "o-", ms=2, lw=1.2, color="#d62728", alpha=0.85)
    ax2.set_title("DL iperf3 Packet Loss — jBPF Exclusive", fontweight="bold")
    ax2.set_ylabel("Loss (%)")
    ax2.set_xlabel("Time (UTC)")
    for ax in (ax1, ax2):
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "17_jbpf_dl_iperf_quality.png", dpi=150)
    plt.close(fig)
    print("  Plot → 17_jbpf_dl_iperf_quality.png")


def _plot_sinr_range(jbpf):
    """Per-slot SINR min/max from fapi_crc_stats (units: ×0.1 dB)."""
    try:
        plt, mdates = _setup_matplotlib()
    except ImportError:
        return
    rows = jbpf.get("fapi_crc", [])
    if not rows:
        return
    ts  = [epoch_to_dt(to_epoch(r["time"])) for r in rows]
    hi  = [float(r["snr_max"]) * _FAPI_SNR_SCALE for r in rows if r.get("snr_max") is not None]
    lo  = [float(r["snr_min"]) * _FAPI_SNR_SCALE for r in rows if r.get("snr_min") is not None]
    t_r = [epoch_to_dt(to_epoch(r["time"])) for r in rows if r.get("snr_max") is not None]
    avg_sinr_rows = jbpf.get("crc", [])
    t_avg = [epoch_to_dt(to_epoch(r["time"])) for r in avg_sinr_rows if r.get("avg_sinr") is not None]
    avg_v = [float(r["avg_sinr"]) for r in avg_sinr_rows if r.get("avg_sinr") is not None]

    fig, ax = plt.subplots()
    if t_r and hi and lo:
        ax.fill_between(t_r, lo, hi, alpha=0.25, color="#1f77b4",
                        label="SINR min–max range (fapi_crc_stats)")
        ax.plot(t_r, hi, lw=0.6, color="#1f77b4", alpha=0.5)
        ax.plot(t_r, lo, lw=0.6, color="#1f77b4", alpha=0.5)
    if t_avg:
        ax.plot(t_avg, avg_v, "o-", ms=2, lw=1.2, color="#ff7f0e",
                label="avg SINR (mac_crc_stats)", alpha=0.85)
    ax.set_title("Per-Slot SINR Range — jBPF Exclusive (fapi_crc_stats)",
                 fontweight="bold")
    ax.set_ylabel("SINR (dB)")
    ax.set_xlabel("Time (UTC)")
    ax.legend(loc="best", fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "18_jbpf_sinr_range.png", dpi=150)
    plt.close(fig)
    print("  Plot → 18_jbpf_sinr_range.png")


def _std_series(rows, field):
    ts, vs = [], []
    for r in rows:
        v = r.get(field)
        if v is not None:
            ts.append(epoch_to_dt(to_epoch(r["time"])))
            vs.append(float(v))
    return ts, vs


def _plot_pucch_pusch_snr(std_ue):
    try:
        plt, mdates = _setup_matplotlib()
    except ImportError:
        return
    t1, v1 = _std_series(std_ue, "pucch_snr_db")
    t2, v2 = _std_series(std_ue, "pusch_snr_db")
    traces = [("PUCCH SNR (control channel)", t1, v1),
              ("PUSCH SNR (data channel)", t2, v2)]
    plot_multi(traces,
               "PUCCH vs PUSCH SNR — Standard Exclusive",
               "SNR (dB)", "19_std_pucch_pusch_snr.png",
               colors=["#9467bd", "#1f77b4"])


def _plot_ta_channels(std_ue):
    t1, v1 = _std_series(std_ue, "pucch_ta_ns")
    t2, v2 = _std_series(std_ue, "pusch_ta_ns")
    t3, v3 = _std_series(std_ue, "ta_ns")
    traces = [("pucch_ta_ns", t1, v1),
              ("pusch_ta_ns", t2, v2),
              ("ta_ns (combined)", t3, v3)]
    plot_multi(traces,
               "Timing Advance — Three Estimates — Standard Exclusive",
               "TA (ns)", "20_std_ta_channels.png",
               colors=["#9467bd", "#1f77b4", "#ff7f0e"])


def _plot_dl_bs(std_ue):
    ts, vs = _std_series(std_ue, "dl_bs")
    if ts:
        plot_single(ts, vs,
                    "DL Buffer Status (dl_bs) — Standard Exclusive",
                    "Pending bytes", "21_std_dl_bs.png",
                    color="#8c564b")


def _plot_harq_delays(std_ue):
    t1, v1 = _std_series(std_ue, "avg_crc_delay")
    t2, v2 = _std_series(std_ue, "avg_pucch_harq_delay")
    t3, v3 = _std_series(std_ue, "avg_pusch_harq_delay")
    traces = [("avg_crc_delay (slots)", t1, v1),
              ("avg_pucch_harq_delay (slots)", t2, v2),
              ("avg_pusch_harq_delay (slots)", t3, v3)]
    plot_multi(traces,
               "HARQ Processing Delays — Standard Exclusive",
               "Delay (slots)", "22_std_harq_delays.png")


def _plot_scheduling_latency(std_cell):
    try:
        plt, mdates = _setup_matplotlib()
    except ImportError:
        return
    if not std_cell:
        return
    t_avg, v_avg = _std_series(std_cell, "average_latency")
    t_max, v_max = _std_series(std_cell, "max_latency")

    # Collect histogram counts across all windows
    hist_cols = [f"latency_histogram_{i}" for i in range(10)]
    hist_totals = np.zeros(10)
    for r in std_cell:
        for i, col in enumerate(hist_cols):
            v = r.get(col)
            if v is not None:
                hist_totals[i] += float(v)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Time series
    if t_avg:
        ax1.plot(t_avg, v_avg, "o-", ms=2, lw=1.2, color="#1f77b4",
                 label="average_latency", alpha=0.85)
    if t_max:
        ax1.plot(t_max, v_max, "s-", ms=2, lw=1, color="#d62728",
                 label="max_latency", alpha=0.7)
    ax1.set_title("Cell Scheduling Latency — Standard Exclusive",
                  fontweight="bold")
    ax1.set_ylabel("Latency (µs)")
    ax1.set_xlabel("Time (UTC)")
    ax1.legend(fontsize=9)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    # Histogram
    bin_labels = [f"bin {i}" for i in range(10)]
    ax2.bar(range(10), hist_totals, color="#1f77b4", alpha=0.8)
    ax2.set_xticks(range(10))
    ax2.set_xticklabels(bin_labels, rotation=30, ha="right")
    ax2.set_title("Scheduling Latency Distribution (cumulative 20 min)",
                  fontweight="bold")
    ax2.set_ylabel("Count of scheduling decisions")
    ax2.set_xlabel("Latency bin (increasing µs ranges)")

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "23_std_scheduling_latency.png", dpi=150)
    plt.close(fig)
    print("  Plot → 23_std_scheduling_latency.png")


def _plot_pucch_rb_usage(std_cell):
    ts, vs = _std_series(std_cell, "pucch_tot_rb_usage_avg")
    if ts:
        plot_single(ts, vs,
                    "PUCCH RB Usage — Standard Exclusive",
                    "Average RBs per slot", "24_std_pucch_rb_usage.png",
                    color="#9467bd")


def _plot_du_latency(std_du):
    try:
        plt, mdates = _setup_matplotlib()
    except ImportError:
        return
    if not std_du:
        return
    t_avg, v_avg = _std_series(std_du, "du_high_mac_dl_0_average_latency_us")
    t_max, v_max = _std_series(std_du, "du_high_mac_dl_0_max_latency_us")
    t_min, v_min = _std_series(std_du, "du_high_mac_dl_0_min_latency_us")

    fig, ax = plt.subplots()
    if t_avg:
        ax.plot(t_avg, v_avg, lw=1.2, color="#1f77b4",
                label="avg latency", alpha=0.85)
    if t_min and t_max:
        ax.fill_between(t_min, v_min, v_max,
                        alpha=0.2, color="#1f77b4", label="min–max range")
    # Slot boundary line (1000 µs at 15 kHz SCS)
    ax.axhline(1000, color="red", lw=1.2, ls="--", alpha=0.7,
               label="slot boundary (1000 µs)")
    ax.set_title("DU High MAC DL Thread Latency — Standard Exclusive",
                 fontweight="bold")
    ax.set_ylabel("Latency (µs)")
    ax.set_xlabel("Time (UTC)")
    ax.legend(fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "25_std_du_latency.png", dpi=150)
    plt.close(fig)
    print("  Plot → 25_std_du_latency.png")


def _plot_std_bler_directions(std_ue):
    """UL and DL HARQ BLER from standard — shows direction asymmetry."""
    try:
        plt, mdates = _setup_matplotlib()
    except ImportError:
        return
    ul_bler, dl_bler, ts_ul, ts_dl = [], [], [], []
    for r in std_ue:
        t = epoch_to_dt(to_epoch(r["time"]))
        ul_ok  = r.get("ul_nof_ok")
        ul_nok = r.get("ul_nof_nok")
        dl_ok  = r.get("dl_nof_ok")
        dl_nok = r.get("dl_nof_nok")
        if ul_ok is not None and ul_nok is not None:
            tot = float(ul_ok) + float(ul_nok)
            if tot > 0:
                ts_ul.append(t)
                ul_bler.append(float(ul_nok) / tot * 100)
        if dl_ok is not None and dl_nok is not None:
            tot = float(dl_ok) + float(dl_nok)
            if tot > 0:
                ts_dl.append(t)
                dl_bler.append(float(dl_nok) / tot * 100)

    fig, ax = plt.subplots()
    if ts_ul:
        ax.plot(ts_ul, ul_bler, "o-", ms=2, lw=1.2, color="#ff7f0e",
                label="UL HARQ BLER (ul_nof_nok/total)", alpha=0.85)
    if ts_dl:
        ax.plot(ts_dl, dl_bler, "s-", ms=2, lw=1.2, color="#1f77b4",
                label="DL HARQ BLER (dl_nof_nok/total)", alpha=0.85)
    ax.set_title("UL vs DL HARQ BLER — Standard (Direction Asymmetry Context)",
                 fontweight="bold")
    ax.set_ylabel("BLER (%)")
    ax.set_xlabel("Time (UTC)")
    ax.legend(fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "26_std_bler_both_directions.png", dpi=150)
    plt.close(fig)
    print("  Plot → 26_std_bler_both_directions.png")


# ─────────────────────────── statistics ──────────────────────────────

def compute_statistics(aligned):
    """Compute summary statistics for each aligned metric pair."""
    stats = {}
    metric_defs = {
        "SINR/SNR (dB)":   ("sinr",    "jbpf_sinr",       "std_sinr"),
        "CQI":             ("cqi",     "jbpf_cqi",        "std_cqi"),
        "DL MCS":          ("dl_mcs",  "jbpf_dl_mcs",     "std_dl_mcs"),
        "UL MCS":          ("ul_mcs",  "jbpf_ul_mcs",     "std_ul_mcs"),
        "DL Mbps":         ("dl_tp",   "jbpf_dl_mbps",    "std_dl_mbps"),
        "UL Mbps":         ("ul_tp",   "jbpf_ul_mbps",    "std_ul_mbps"),
        "UL BLER %":       ("ul_bler", "jbpf_ul_bler_pct","std_ul_bler_pct"),
        "BSR (bytes)":     ("bsr",     "jbpf_bsr",        "std_bsr"),
        "TA (ns)":         ("ta",      "jbpf_ta_ns",      "std_ta_ns"),
        "RI":              ("ri",      "jbpf_ri",         "std_ri"),
    }
    for name, (key, jk, sk) in metric_defs.items():
        series = aligned.get(key, [])
        jv = [float(r[jk]) for r in series if r.get(jk) is not None]
        sv = [float(r[sk]) for r in series if r.get(sk) is not None]
        n  = min(len(jv), len(sv))
        if jv and sv and n > 0:
            corr = (np.corrcoef(jv[:n], sv[:n])[0, 1]
                    if n > 2 else float("nan"))
            stats[name] = {
                "jbpf_mean": float(np.mean(jv)),
                "jbpf_std":  float(np.std(jv)),
                "jbpf_min":  float(np.min(jv)),
                "jbpf_max":  float(np.max(jv)),
                "jbpf_n":    len(jv),
                "std_mean":  float(np.mean(sv)),
                "std_std":   float(np.std(sv)),
                "std_min":   float(np.min(sv)),
                "std_max":   float(np.max(sv)),
                "std_n":     len(sv),
                "correlation":    float(corr),
                "mean_diff_pct":  float(
                    abs(np.mean(jv) - np.mean(sv)) /
                    max(abs(np.mean(sv)), 1e-9) * 100
                ),
            }
    return stats


def print_statistics(stats):
    print("\n" + "=" * 108)
    print("STATISTICAL COMPARISON: jBPF vs Standard Telemetry")
    print("=" * 108)
    print(f"{'Metric':<16} {'jBPF Mean':>11} {'jBPF Std':>10} {'Std Mean':>11} "
          f"{'Std Std':>10} {'Corr':>8} {'Diff%':>8} {'jBPF N':>7} {'Std N':>7}")
    print("-" * 108)
    for name, s in stats.items():
        print(f"{name:<16} {s['jbpf_mean']:>11.3f} {s['jbpf_std']:>10.3f} "
              f"{s['std_mean']:>11.3f} {s['std_std']:>10.3f} "
              f"{s['correlation']:>8.3f} {s['mean_diff_pct']:>7.1f}% "
              f"{s['jbpf_n']:>7} {s['std_n']:>7}")
    print("=" * 108)


# ─────────────────────────────── main ────────────────────────────────

def main():
    global TIME_START, TIME_END

    parser = argparse.ArgumentParser(
        description="jBPF vs Standard telemetry: extract, align, plot, stats"
    )
    parser.add_argument("--start", help="Start time (ISO, e.g. 2026-04-03T10:36:00Z)")
    parser.add_argument("--end",   help="End time (ISO, e.g. 2026-04-03T11:33:00Z)")
    parser.add_argument("--trim-startup", type=int, default=30,
                        help="Seconds to trim from session start (default: 30)")
    args = parser.parse_args()

    TIME_START = args.start
    TIME_END   = args.end
    if TIME_START or TIME_END:
        print(f"  Time window: {TIME_START or '...'} → {TIME_END or '...'}")

    jbpf     = extract_jbpf()
    standard = extract_standard()

    std_ue = standard["ue"]

    # Auto-detect session boundary: find the largest gap in the standard ue
    # time series and use the point after that gap as the session start.
    # This removes data from previous gNB runs stored in the same database.
    if not TIME_START and std_ue:
        times = [to_epoch(r["time"]) for r in std_ue]
        gaps  = [(times[i+1] - times[i], times[i+1])
                 for i in range(len(times) - 1)]
        max_gap, session_start = max(gaps, key=lambda x: x[0])
        if max_gap > 30:   # only apply if the gap is larger than 30 s
            print(f"  Detected session gap of {max_gap:.0f} s; "
                  f"using data from "
                  f"{datetime.fromtimestamp(session_start, tz=timezone.utc).strftime('%H:%M:%S')} onwards")
            for table in ("ue", "cell", "du", "events"):
                if standard.get(table):
                    standard[table] = [
                        r for r in standard[table]
                        if to_epoch(r["time"]) >= session_start
                    ]
            for key in list(jbpf.keys()):
                rows = jbpf[key]
                if rows and "time" in rows[0]:
                    jbpf[key] = [r for r in rows
                                 if to_epoch(r["time"]) >= session_start]
            std_ue = standard["ue"]

    # Trim startup transients from the beginning of the identified session
    if not TIME_START and args.trim_startup > 0 and std_ue:
        cutoff = to_epoch(std_ue[0]["time"]) + args.trim_startup
        standard["ue"] = [r for r in std_ue if to_epoch(r["time"]) >= cutoff]
        for table in ("cell", "du", "events"):
            if standard.get(table):
                standard[table] = [
                    r for r in standard[table]
                    if to_epoch(r["time"]) >= cutoff
                ]
        for key in list(jbpf.keys()):
            rows = jbpf[key]
            if rows and "time" in rows[0]:
                jbpf[key] = [r for r in rows if to_epoch(r["time"]) >= cutoff]
        std_ue = standard["ue"]
        print(f"  Trimmed first {args.trim_startup} s of startup transient")

    aligned = build_aligned_series(jbpf, std_ue)
    stats   = compute_statistics(aligned)
    print_statistics(stats)
    make_plots(aligned, jbpf, standard)

    # Persist statistics as JSON
    stats_path = CSV_DIR / "statistics.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\n  Stats → {stats_path}")
    print(f"\nAll outputs in: {OUT_DIR}")
    print(f"Plots:          {PLOT_DIR}")
    print(f"CSVs:           {CSV_DIR}")


if __name__ == "__main__":
    main()
