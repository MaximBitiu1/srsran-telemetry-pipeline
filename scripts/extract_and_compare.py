#!/usr/bin/env python3
"""
jBPF vs srsRAN Standard Telemetry — Data Extraction, Comparison & Plotting
===========================================================================
Extracts overlapping metrics from both telemetry sources (jBPF eBPF codelets
via InfluxDB 1.x on :8086 and srsRAN built-in Grafana GUI via InfluxDB 3 on
:8081), aligns them in time, produces CSV exports, comparison plots, and
statistical analysis for thesis documentation.
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

# ── Output directory ──────────────────────────────────────────────────
OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "comparison"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PLOT_DIR = OUT_DIR / "figures"
PLOT_DIR.mkdir(parents=True, exist_ok=True)
CSV_DIR  = OUT_DIR / "data"
CSV_DIR.mkdir(parents=True, exist_ok=True)

JBPF_URL = "http://localhost:8086"
JBPF_DB  = "srsran_telemetry"
STD_URL  = "http://localhost:8081"
STD_DB   = "srsran"

# Time window (set by CLI args, None = no filter)
TIME_START = None   # ISO string e.g. '2026-04-03T10:36:00Z'
TIME_END   = None   # ISO string


# ────────────────────────────── helpers ──────────────────────────────

def _time_clause_influx1():
    """Build InfluxQL WHERE clauses for the time window."""
    parts = []
    if TIME_START:
        parts.append(f"time >= '{TIME_START}'")
    if TIME_END:
        parts.append(f"time <= '{TIME_END}'")
    return (" AND ".join(parts)) if parts else ""


def _time_clause_sql():
    """Build SQL WHERE clauses for InfluxDB 3."""
    parts = []
    if TIME_START:
        parts.append(f"time >= '{TIME_START}'")
    if TIME_END:
        parts.append(f"time <= '{TIME_END}'")
    return (" AND ".join(parts)) if parts else ""


def _inject_where(q, clause):
    """Inject a WHERE/AND clause into a query that may already have WHERE."""
    if not clause:
        return q
    q_upper = q.upper()
    if "WHERE" in q_upper:
        # Insert after existing WHERE
        idx = q_upper.index("WHERE") + len("WHERE")
        return q[:idx] + " " + clause + " AND" + q[idx:]
    # Insert before ORDER BY / GROUP BY / LIMIT
    for kw in ("ORDER BY", "GROUP BY", "LIMIT"):
        if kw in q_upper:
            idx = q_upper.index(kw)
            return q[:idx] + "WHERE " + clause + " " + q[idx:]
    return q + " WHERE " + clause


def query_influx1(q: str):
    """Query InfluxDB 1.x and return list of dicts."""
    q = _inject_where(q, _time_clause_influx1())
    url = f"{JBPF_URL}/query?db={JBPF_DB}&q={urllib.parse.quote(q)}"
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.loads(r.read())
    results = []
    for stmt in data.get("results", []):
        for series in stmt.get("series", []):
            cols = series["columns"]
            for row in series["values"]:
                results.append(dict(zip(cols, row)))
    return results


def query_influx3(q: str):
    """Query InfluxDB 3 (SQL) and return list of dicts."""
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
    """Convert ISO timestamp to epoch seconds."""
    ts_str = ts_str.rstrip("Z")
    # Truncate fractional seconds to 6 digits (microseconds) for strptime
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
    raise ValueError(f"Cannot parse timestamp: {ts_str}")


def save_csv(rows, filename):
    if not rows:
        return
    path = CSV_DIR / filename
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"  Saved {len(rows)} rows → {path}")


# ───────────────────────── data extraction ──────────────────────────

def extract_jbpf():
    """Extract all jBPF metrics into per-measurement dicts."""
    print("[1/4] Extracting jBPF telemetry from InfluxDB 1.x …")
    datasets = {}

    # CRC stats (SINR, RSRP, tx success)
    rows = query_influx1(
        "SELECT * FROM mac_crc_stats ORDER BY time ASC"
    )
    datasets["crc"] = rows
    save_csv(rows, "jbpf_crc_stats.csv")

    # UCI stats (CQI, RI, TA, SR)
    rows = query_influx1(
        "SELECT * FROM mac_uci_stats ORDER BY time ASC"
    )
    datasets["uci"] = rows
    save_csv(rows, "jbpf_uci_stats.csv")

    # HARQ stats (MCS, retx)
    rows = query_influx1(
        "SELECT * FROM mac_harq_stats ORDER BY time ASC"
    )
    datasets["harq"] = rows
    save_csv(rows, "jbpf_harq_stats.csv")

    # BSR
    rows = query_influx1(
        "SELECT * FROM mac_bsr_stats ORDER BY time ASC"
    )
    datasets["bsr"] = rows
    save_csv(rows, "jbpf_bsr_stats.csv")

    # FAPI DL config (PRBs, MCS, TBS)
    rows = query_influx1(
        "SELECT * FROM fapi_dl_config ORDER BY time ASC"
    )
    datasets["fapi_dl"] = rows
    save_csv(rows, "jbpf_fapi_dl.csv")

    # FAPI UL config
    rows = query_influx1(
        "SELECT * FROM fapi_ul_config ORDER BY time ASC"
    )
    datasets["fapi_ul"] = rows
    save_csv(rows, "jbpf_fapi_ul.csv")

    # FAPI CRC (SNR range, TA range)
    rows = query_influx1(
        "SELECT * FROM fapi_crc_stats ORDER BY time ASC"
    )
    datasets["fapi_crc"] = rows
    save_csv(rows, "jbpf_fapi_crc.csv")

    # Throughput
    for direction in ("dl", "ul"):
        rows = query_influx1(
            f"SELECT * FROM ue_{direction}_throughput ORDER BY time ASC"
        )
        datasets[f"tp_{direction}"] = rows
        save_csv(rows, f"jbpf_throughput_{direction}.csv")

    # RTT
    rows = query_influx1("SELECT * FROM ue_rtt ORDER BY time ASC")
    datasets["rtt"] = rows
    save_csv(rows, "jbpf_rtt.csv")

    # jBPF perf
    rows = query_influx1("SELECT * FROM jbpf_perf ORDER BY time ASC")
    datasets["perf"] = rows
    save_csv(rows, "jbpf_perf.csv")

    return datasets


def extract_standard():
    """Extract srsRAN standard metrics from InfluxDB 3."""
    print("[2/4] Extracting srsRAN standard metrics from InfluxDB 3 …")
    rows = query_influx3(
        "SELECT time, dl_brate, ul_brate, dl_mcs, ul_mcs, "
        "dl_nof_ok, dl_nof_nok, ul_nof_ok, ul_nof_nok, "
        "cqi, pusch_snr_db, pucch_snr_db, ta_ns, "
        "bsr, dl_bs, dl_ri, ul_ri "
        "FROM ue ORDER BY time ASC"
    )
    save_csv(rows, "standard_ue_metrics.csv")
    print(f"  Standard: {len(rows)} rows")
    return rows


# ─────────────────────── time-aligned merge ─────────────────────────

def build_aligned_series(jbpf, standard):
    """
    Build time-aligned series for each overlapping metric.
    jBPF reports every ~2s, standard every ~2-3s.
    We align by nearest-neighbour within ±3s window.
    """
    print("[3/4] Aligning time series …")

    # Parse timestamps
    std_times = np.array([to_epoch(r["time"]) for r in standard])

    def nearest_std(t, field):
        """Find nearest standard row within ±3s."""
        diffs = np.abs(std_times - t)
        idx = np.argmin(diffs)
        if diffs[idx] <= 3.0:
            return standard[idx].get(field)
        return None

    aligned = {}

    # 1. SINR / SNR
    crc = jbpf.get("crc", [])
    if crc:
        series = []
        for r in crc:
            t = to_epoch(r["time"])
            std_snr = nearest_std(t, "pusch_snr_db")
            series.append({
                "time": r["time"],
                "epoch": t,
                "jbpf_sinr": r.get("avg_sinr"),
                "std_snr": std_snr,
            })
        aligned["sinr_snr"] = series
        save_csv(series, "aligned_sinr_snr.csv")

    # 2. CQI
    uci = jbpf.get("uci", [])
    if uci:
        series = []
        for r in uci:
            t = to_epoch(r["time"])
            std_cqi = nearest_std(t, "cqi")
            series.append({
                "time": r["time"],
                "epoch": t,
                "jbpf_cqi": r.get("avg_cqi"),
                "std_cqi": std_cqi,
            })
        aligned["cqi"] = series
        save_csv(series, "aligned_cqi.csv")

    # 3. DL MCS
    fapi_dl = jbpf.get("fapi_dl", [])
    if fapi_dl:
        series = []
        for r in fapi_dl:
            t = to_epoch(r["time"])
            std_mcs = nearest_std(t, "dl_mcs")
            series.append({
                "time": r["time"],
                "epoch": t,
                "jbpf_dl_mcs": r.get("avg_mcs"),
                "std_dl_mcs": std_mcs,
            })
        aligned["dl_mcs"] = series
        save_csv(series, "aligned_dl_mcs.csv")

    # 4. UL MCS
    fapi_ul = jbpf.get("fapi_ul", [])
    if fapi_ul:
        series = []
        for r in fapi_ul:
            t = to_epoch(r["time"])
            std_mcs = nearest_std(t, "ul_mcs")
            series.append({
                "time": r["time"],
                "epoch": t,
                "jbpf_ul_mcs": r.get("avg_mcs"),
                "std_ul_mcs": std_mcs,
            })
        aligned["ul_mcs"] = series
        save_csv(series, "aligned_ul_mcs.csv")

    # 5. DL Bitrate  (jBPF=Mbps from iperf3, std=bps from gNB MAC)
    tp_dl = jbpf.get("tp_dl", [])
    if tp_dl:
        series = []
        for r in tp_dl:
            t = to_epoch(r["time"])
            std_val = nearest_std(t, "dl_brate")
            series.append({
                "time": r["time"],
                "epoch": t,
                "jbpf_dl_mbps": r.get("bitrate_mbps"),
                "std_dl_bps": std_val,
                "std_dl_mbps": float(std_val) / 1e6 if std_val is not None else None,
            })
        aligned["dl_brate"] = series
        save_csv(series, "aligned_dl_bitrate.csv")

    # 6. UL Bitrate
    tp_ul = jbpf.get("tp_ul", [])
    if tp_ul:
        series = []
        for r in tp_ul:
            t = to_epoch(r["time"])
            std_val = nearest_std(t, "ul_brate")
            series.append({
                "time": r["time"],
                "epoch": t,
                "jbpf_ul_mbps": r.get("bitrate_mbps"),
                "std_ul_bps": std_val,
                "std_ul_mbps": float(std_val) / 1e6 if std_val is not None else None,
            })
        aligned["ul_brate"] = series
        save_csv(series, "aligned_ul_bitrate.csv")

    # 7. BSR
    bsr = jbpf.get("bsr", [])
    if bsr:
        series = []
        for r in bsr:
            t = to_epoch(r["time"])
            std_bsr = nearest_std(t, "bsr")
            series.append({
                "time": r["time"],
                "epoch": t,
                "jbpf_bsr_bytes": r.get("total_bytes"),
                "std_bsr": std_bsr,
            })
        aligned["bsr"] = series
        save_csv(series, "aligned_bsr.csv")

    # 8. Timing Advance
    if uci:
        series = []
        for r in uci:
            t = to_epoch(r["time"])
            std_ta = nearest_std(t, "ta_ns")
            series.append({
                "time": r["time"],
                "epoch": t,
                "jbpf_ta": r.get("avg_timing_advance"),
                "std_ta_ns": std_ta,
            })
        aligned["ta"] = series
        save_csv(series, "aligned_ta.csv")

    # 9. BLER / TX Success
    if crc:
        series = []
        for r in crc:
            t = to_epoch(r["time"])
            std_ok = nearest_std(t, "dl_nof_ok")
            std_nok = nearest_std(t, "dl_nof_nok")
            std_bler = None
            if std_ok is not None and std_nok is not None:
                total = float(std_ok) + float(std_nok)
                std_bler = float(std_nok) / total * 100 if total > 0 else 0.0
            series.append({
                "time": r["time"],
                "epoch": t,
                "jbpf_tx_success_pct": r.get("tx_success_rate"),
                "jbpf_bler_pct": 100.0 - float(r["tx_success_rate"]) if r.get("tx_success_rate") is not None else None,
                "std_bler_pct": std_bler,
            })
        aligned["bler"] = series
        save_csv(series, "aligned_bler.csv")

    return aligned


# ───────────────────────────── plotting ─────────────────────────────

def make_plots(aligned, jbpf, standard):
    """Generate comparison plots."""
    print("[4/4] Generating plots …")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("  matplotlib not installed — skipping plots")
        return

    plt.rcParams.update({
        "figure.figsize": (12, 5),
        "font.size": 11,
        "axes.grid": True,
        "grid.alpha": 0.3,
    })

    def epoch_to_dt(ep):
        return datetime.fromtimestamp(ep, tz=timezone.utc)

    def plot_dual(series, jbpf_key, std_key, title, ylabel, fname,
                  jbpf_label="jBPF (eBPF codelets)", std_label="Standard (Grafana GUI)"):
        fig, ax = plt.subplots()
        jt, jv, st, sv = [], [], [], []
        for r in series:
            if r.get(jbpf_key) is not None:
                jt.append(epoch_to_dt(r["epoch"]))
                jv.append(float(r[jbpf_key]))
            if r.get(std_key) is not None:
                st.append(epoch_to_dt(r["epoch"]))
                sv.append(float(r[std_key]))
        if jt:
            ax.plot(jt, jv, "o-", markersize=3, linewidth=1.2,
                    color="#1f77b4", label=jbpf_label, alpha=0.85)
        if st:
            ax.plot(st, sv, "s-", markersize=3, linewidth=1.2,
                    color="#ff7f0e", label=std_label, alpha=0.85)
        ax.set_title(title, fontweight="bold")
        ax.set_ylabel(ylabel)
        ax.set_xlabel("Time (UTC)")
        ax.legend(loc="best")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(PLOT_DIR / fname, dpi=150)
        plt.close(fig)
        print(f"  Plot → {fname}")

    # 1. SINR vs SNR
    if "sinr_snr" in aligned:
        plot_dual(aligned["sinr_snr"], "jbpf_sinr", "std_snr",
                  "SINR / SNR Comparison", "dB",
                  "01_sinr_snr_comparison.png",
                  "jBPF SINR (MAC CRC)", "Standard PUSCH SNR")

    # 2. CQI
    if "cqi" in aligned:
        plot_dual(aligned["cqi"], "jbpf_cqi", "std_cqi",
                  "CQI Comparison", "CQI Index",
                  "02_cqi_comparison.png")

    # 3. DL MCS
    if "dl_mcs" in aligned:
        plot_dual(aligned["dl_mcs"], "jbpf_dl_mcs", "std_dl_mcs",
                  "DL MCS Comparison", "MCS Index",
                  "03_dl_mcs_comparison.png",
                  "jBPF (FAPI DL)", "Standard")

    # 4. UL MCS
    if "ul_mcs" in aligned:
        plot_dual(aligned["ul_mcs"], "jbpf_ul_mcs", "std_ul_mcs",
                  "UL MCS Comparison", "MCS Index",
                  "04_ul_mcs_comparison.png",
                  "jBPF (FAPI UL)", "Standard")

    # 5. DL Bitrate
    if "dl_brate" in aligned:
        plot_dual(aligned["dl_brate"], "jbpf_dl_mbps", "std_dl_mbps",
                  "DL Throughput Comparison", "Mbps",
                  "05_dl_throughput_comparison.png",
                  "jBPF (iperf3 DL)", "Standard (MAC DL brate)")

    # 6. UL Bitrate
    if "ul_brate" in aligned:
        plot_dual(aligned["ul_brate"], "jbpf_ul_mbps", "std_ul_mbps",
                  "UL Throughput Comparison", "Mbps",
                  "06_ul_throughput_comparison.png",
                  "jBPF (iperf3 UL)", "Standard (MAC UL brate)")

    # 7. BLER
    if "bler" in aligned:
        plot_dual(aligned["bler"], "jbpf_bler_pct", "std_bler_pct",
                  "DL BLER Comparison", "BLER %",
                  "07_bler_comparison.png",
                  "jBPF (1 - TX success)", "Standard (nok/total)")

    # 8. BSR
    if "bsr" in aligned:
        plot_dual(aligned["bsr"], "jbpf_bsr_bytes", "std_bsr",
                  "Buffer Status Reports Comparison", "Bytes",
                  "08_bsr_comparison.png",
                  "jBPF (BSR total bytes)", "Standard BSR")

    # 9. Timing Advance
    if "ta" in aligned:
        plot_dual(aligned["ta"], "jbpf_ta", "std_ta_ns",
                  "Timing Advance Comparison", "ns / value",
                  "09_ta_comparison.png",
                  "jBPF (UCI TA)", "Standard (ta_ns)")

    # ── jBPF-exclusive metrics ────────────────────────────────────

    # 10. jBPF Hook Latency
    perf = jbpf.get("perf", [])
    if perf:
        fig, ax = plt.subplots()
        times = [epoch_to_dt(to_epoch(r["time"])) for r in perf]
        hooks = set()
        for r in perf:
            if r.get("hook"):
                hooks.add(r["hook"])
        for hook in sorted(hooks):
            pts = [(t, float(r.get("p50", 0))/1000)
                   for t, r in zip(times, perf)
                   if r.get("hook") == hook and r.get("p50")]
            if pts:
                ax.plot([p[0] for p in pts], [p[1] for p in pts],
                        "o-", markersize=2, linewidth=1, label=hook, alpha=0.7)
        ax.set_title("jBPF Hook Latency (p50) — jBPF Exclusive", fontweight="bold")
        ax.set_ylabel("Latency (µs)")
        ax.set_xlabel("Time (UTC)")
        if len(hooks) <= 8:
            ax.legend(loc="best", fontsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(PLOT_DIR / "10_jbpf_hook_latency.png", dpi=150)
        plt.close(fig)
        print("  Plot → 10_jbpf_hook_latency.png")

    # 11. RTT (jBPF-exclusive)
    rtt = jbpf.get("rtt", [])
    if rtt:
        fig, ax = plt.subplots()
        times = [epoch_to_dt(to_epoch(r["time"])) for r in rtt if r.get("rtt_ms")]
        vals  = [float(r["rtt_ms"]) for r in rtt if r.get("rtt_ms")]
        if times:
            ax.plot(times, vals, "o-", markersize=2, linewidth=1,
                    color="#2ca02c", alpha=0.8)
            ax.set_title("Ping RTT — jBPF Exclusive", fontweight="bold")
            ax.set_ylabel("RTT (ms)")
            ax.set_xlabel("Time (UTC)")
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
            fig.autofmt_xdate()
            fig.tight_layout()
            fig.savefig(PLOT_DIR / "11_jbpf_rtt.png", dpi=150)
            plt.close(fig)
            print("  Plot → 11_jbpf_rtt.png")

    # 12. Summary statistics bar chart
    stats = compute_statistics(aligned)
    if stats:
        metrics = list(stats.keys())
        jbpf_means = [stats[m]["jbpf_mean"] for m in metrics]
        std_means  = [stats[m]["std_mean"] for m in metrics]

        fig, ax = plt.subplots(figsize=(14, 6))
        x = np.arange(len(metrics))
        w = 0.35
        bars1 = ax.bar(x - w/2, jbpf_means, w, label="jBPF", color="#1f77b4", alpha=0.85)
        bars2 = ax.bar(x + w/2, std_means, w, label="Standard", color="#ff7f0e", alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels(metrics, rotation=30, ha="right")
        ax.set_title("Mean Value Comparison — jBPF vs Standard Telemetry", fontweight="bold")
        ax.set_ylabel("Mean Value")
        ax.legend()
        fig.tight_layout()
        fig.savefig(PLOT_DIR / "12_summary_bar_chart.png", dpi=150)
        plt.close(fig)
        print("  Plot → 12_summary_bar_chart.png")

    # 13. Correlation scatter plots
    plot_correlations(aligned)


def plot_correlations(aligned):
    """Scatter plots showing correlation between jBPF and standard."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    pairs = [
        ("sinr_snr", "jbpf_sinr", "std_snr", "SINR (jBPF) vs SNR (Std)", "dB"),
        ("cqi", "jbpf_cqi", "std_cqi", "CQI", "Index"),
        ("dl_mcs", "jbpf_dl_mcs", "std_dl_mcs", "DL MCS", "Index"),
        ("dl_brate", "jbpf_dl_mbps", "std_dl_mbps", "DL Throughput", "Mbps"),
        ("ul_brate", "jbpf_ul_mbps", "std_ul_mbps", "UL Throughput", "Mbps"),
    ]

    fig, axes = plt.subplots(1, len(pairs), figsize=(20, 4))
    for i, (key, jk, sk, title, unit) in enumerate(pairs):
        ax = axes[i]
        series = aligned.get(key, [])
        jv, sv = [], []
        for r in series:
            if r.get(jk) is not None and r.get(sk) is not None:
                jv.append(float(r[jk]))
                sv.append(float(r[sk]))
        if jv:
            ax.scatter(jv, sv, s=15, alpha=0.6, color="#1f77b4")
            # 1:1 line
            lo = min(min(jv), min(sv))
            hi = max(max(jv), max(sv))
            ax.plot([lo, hi], [lo, hi], "k--", linewidth=0.8, alpha=0.5)
            # Correlation
            if len(jv) > 2:
                corr = np.corrcoef(jv, sv)[0, 1]
                ax.text(0.05, 0.95, f"r = {corr:.3f}",
                        transform=ax.transAxes, fontsize=9,
                        verticalalignment="top",
                        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))
        ax.set_xlabel(f"jBPF ({unit})")
        ax.set_ylabel(f"Standard ({unit})")
        ax.set_title(title, fontsize=10)
    fig.suptitle("Correlation: jBPF vs Standard Telemetry", fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "13_correlation_scatter.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  Plot → 13_correlation_scatter.png")


# ──────────────────────── statistics ─────────────────────────────

def compute_statistics(aligned):
    """Compute summary statistics for each aligned metric."""
    stats = {}
    metric_defs = {
        "SINR/SNR (dB)":   ("sinr_snr", "jbpf_sinr", "std_snr"),
        "CQI":             ("cqi", "jbpf_cqi", "std_cqi"),
        "DL MCS":          ("dl_mcs", "jbpf_dl_mcs", "std_dl_mcs"),
        "UL MCS":          ("ul_mcs", "jbpf_ul_mcs", "std_ul_mcs"),
        "DL Mbps":         ("dl_brate", "jbpf_dl_mbps", "std_dl_mbps"),
        "UL Mbps":         ("ul_brate", "jbpf_ul_mbps", "std_ul_mbps"),
        "BLER %":          ("bler", "jbpf_bler_pct", "std_bler_pct"),
    }

    for name, (key, jk, sk) in metric_defs.items():
        series = aligned.get(key, [])
        jv = [float(r[jk]) for r in series if r.get(jk) is not None]
        sv = [float(r[sk]) for r in series if r.get(sk) is not None]
        if jv and sv:
            corr = np.corrcoef(jv[:min(len(jv),len(sv))],
                               sv[:min(len(jv),len(sv))])[0,1] if min(len(jv),len(sv)) > 2 else float("nan")
            stats[name] = {
                "jbpf_mean": np.mean(jv),
                "jbpf_std":  np.std(jv),
                "jbpf_min":  np.min(jv),
                "jbpf_max":  np.max(jv),
                "jbpf_n":    len(jv),
                "std_mean":  np.mean(sv),
                "std_std":   np.std(sv),
                "std_min":   np.min(sv),
                "std_max":   np.max(sv),
                "std_n":     len(sv),
                "correlation": corr,
                "mean_diff_pct": abs(np.mean(jv) - np.mean(sv)) / max(np.mean(sv), 1e-9) * 100,
            }
    return stats


def print_statistics(stats):
    """Print formatted statistics table."""
    print("\n" + "="*100)
    print("STATISTICAL COMPARISON: jBPF vs Standard Telemetry")
    print("="*100)
    print(f"{'Metric':<16} {'jBPF Mean':>10} {'jBPF Std':>10} {'Std Mean':>10} "
          f"{'Std Std':>10} {'Corr':>8} {'Diff%':>8} {'jBPF N':>7} {'Std N':>7}")
    print("-"*100)
    for name, s in stats.items():
        print(f"{name:<16} {s['jbpf_mean']:>10.2f} {s['jbpf_std']:>10.3f} "
              f"{s['std_mean']:>10.2f} {s['std_std']:>10.3f} "
              f"{s['correlation']:>8.3f} {s['mean_diff_pct']:>7.1f}% "
              f"{s['jbpf_n']:>7} {s['std_n']:>7}")
    print("="*100)
    return stats


# ───────────────────────────── main ─────────────────────────────────

def main():
    global TIME_START, TIME_END

    parser = argparse.ArgumentParser(description="jBPF vs Standard telemetry comparison")
    parser.add_argument("--start", help="Start time (ISO, e.g. 2026-04-03T10:36:00Z)")
    parser.add_argument("--end",   help="End time (ISO, e.g. 2026-04-03T11:33:00Z)")
    parser.add_argument("--trim-startup", type=int, default=30,
                        help="Seconds to trim from session start (default: 30)")
    args = parser.parse_args()

    TIME_START = args.start
    TIME_END = args.end

    if TIME_START or TIME_END:
        print(f"  Time window: {TIME_START or '...'} → {TIME_END or '...'}")

    jbpf = extract_jbpf()
    standard = extract_standard()

    # Auto-trim startup transients if no explicit start was given
    if not TIME_START and args.trim_startup > 0 and standard:
        first_t = to_epoch(standard[0]["time"])
        cutoff = first_t + args.trim_startup
        standard = [r for r in standard if to_epoch(r["time"]) >= cutoff]
        for key in list(jbpf.keys()):
            rows = jbpf[key]
            if rows and "time" in rows[0]:
                jbpf[key] = [r for r in rows if to_epoch(r["time"]) >= cutoff]
        print(f"  Trimmed first {args.trim_startup}s of startup transient")

    aligned = build_aligned_series(jbpf, standard)
    stats = compute_statistics(aligned)
    print_statistics(stats)
    make_plots(aligned, jbpf, standard)

    # Save stats as JSON for the markdown page
    stats_path = CSV_DIR / "statistics.json"
    # Convert numpy types to native python
    clean_stats = {}
    for k, v in stats.items():
        clean_stats[k] = {kk: (float(vv) if isinstance(vv, (np.floating, np.integer)) else vv)
                          for kk, vv in v.items()}
    with open(stats_path, "w") as f:
        json.dump(clean_stats, f, indent=2)
    print(f"\n  Stats → {stats_path}")
    print(f"\nAll outputs in: {OUT_DIR}")


if __name__ == "__main__":
    main()
