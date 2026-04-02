#!/usr/bin/env python3
"""Generate cross-scenario comparison plots for both datasets."""

import csv
from pathlib import Path
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STRESS_DIR = Path.home() / "Desktop/datasets/stress_anomaly"
CHANNEL_DIR = Path.home() / "Desktop/datasets/channel"

FAPI_UL_HOOK = "fapi_ul_tti_request"

# Colour maps
CHANNEL_COLORS = {
    "baseline": "steelblue",
    "time_varying": "darkorange",
    "steady_impairment": "crimson",
    "rlf_cycle": "mediumpurple",
}

STRESS_COLORS = {
    "baseline": "steelblue",
    "cpu": "darkorange",
    "memory": "crimson",
    "sched": "mediumpurple",
    "traffic": "forestgreen",
    "combined": "goldenrod",
}


def read_csv(path: Path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def scenario_meta(rows):
    """Return dict scenario_id -> (label, category) from first row."""
    meta = {}
    for r in rows:
        sid = r["scenario_id"]
        if sid not in meta:
            meta[sid] = (r["label"], r["category"])
    return meta


# ---------------------------------------------------------------------------
# Channel dataset summary
# ---------------------------------------------------------------------------

def channel_summary():
    csv_dir = CHANNEL_DIR / "csv"
    plots_dir = CHANNEL_DIR / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    harq_all = read_csv(csv_dir / "harq_stats.csv")
    bsr_all = read_csv(csv_dir / "bsr_stats.csv")
    rlc_all = read_csv(csv_dir / "rlc_ul_stats.csv")
    crc_all = read_csv(csv_dir / "crc_stats.csv")

    # Only MAC scenarios
    mac_sids = ["B1", "B2", "T1", "T2", "S1", "S2", "L1"]

    meta = {}
    for rows in [harq_all, bsr_all, rlc_all, crc_all]:
        meta.update(scenario_meta(rows))

    # Compute per-scenario aggregates
    mcs_avg = {}
    for r in harq_all:
        sid = r["scenario_id"]
        if sid not in mac_sids:
            continue
        mcs_avg.setdefault(sid, []).append(float(r["avg_mcs"]))
    mcs_avg = {sid: np.mean(vals) for sid, vals in mcs_avg.items()}

    bsr_max = {}
    for r in bsr_all:
        sid = r["scenario_id"]
        if sid not in mac_sids:
            continue
        bsr_max[sid] = max(bsr_max.get(sid, 0), int(r["bytes"]))
    # Convert to MB
    bsr_max_mb = {sid: val / (1024 * 1024) for sid, val in bsr_max.items()}

    rlc_max_ms = {}
    for r in rlc_all:
        sid = r["scenario_id"]
        if sid not in mac_sids:
            continue
        val = float(r["sdu_delivered_lat_max_us"]) / 1000  # us -> ms
        rlc_max_ms[sid] = max(rlc_max_ms.get(sid, 0), val)

    # HARQ failure rate: total failures / duration
    harq_fail = defaultdict(lambda: {"failures": 0, "max_t": 0})
    for r in crc_all:
        sid = r["scenario_id"]
        if sid not in mac_sids:
            continue
        harq_fail[sid]["failures"] += int(r["harq_failure"])
        harq_fail[sid]["max_t"] = max(harq_fail[sid]["max_t"], float(r["relative_s"]))
    harq_fail_rate = {}
    for sid, d in harq_fail.items():
        dur = d["max_t"] if d["max_t"] > 0 else 1
        harq_fail_rate[sid] = d["failures"] / dur

    # Plot
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Channel Dataset - Cross-Scenario Summary", fontsize=14, fontweight="bold")

    for ax_idx, (ax, title, data, ylabel, use_log) in enumerate([
        (axes[0, 0], "Average MCS", mcs_avg, "MCS", False),
        (axes[0, 1], "BSR Max (MB)", bsr_max_mb, "MB", True),
        (axes[1, 0], "RLC Delivery Delay Max (ms)", rlc_max_ms, "ms", True),
        (axes[1, 1], "HARQ Failure Rate (/s)", harq_fail_rate, "/s", False),
    ]):
        sids_ordered = [s for s in mac_sids if s in data]
        vals = [data[s] for s in sids_ordered]
        colors = [CHANNEL_COLORS.get(meta.get(s, ("", "unknown"))[1], "gray") for s in sids_ordered]
        labels = [f"{s}\n{meta.get(s, ('',''))[0][:15]}" for s in sids_ordered]

        bars = ax.bar(labels, vals, color=colors, edgecolor="black", linewidth=0.5)
        ax.set_title(title, fontsize=11)
        ax.set_ylabel(ylabel)
        if use_log and any(v > 0 for v in vals):
            ax.set_yscale("log")
        ax.tick_params(axis="x", labelsize=8)

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, edgecolor="black", label=cat)
                       for cat, c in CHANNEL_COLORS.items()]
    fig.legend(handles=legend_elements, loc="lower center", ncol=4, fontsize=9,
               bbox_to_anchor=(0.5, -0.02))

    plt.tight_layout(rect=[0, 0.04, 1, 0.96])
    out = plots_dir / "channel_summary.png"
    fig.savefig(str(out), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


# ---------------------------------------------------------------------------
# Stress dataset summary
# ---------------------------------------------------------------------------

def stress_summary():
    csv_dir = STRESS_DIR / "csv"
    plots_dir = STRESS_DIR / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    perf_all = read_csv(csv_dir / "jbpf_out_perf_list.csv")
    bsr_all = read_csv(csv_dir / "bsr_stats.csv")

    meta = {}
    for rows in [perf_all, bsr_all]:
        meta.update(scenario_meta(rows))

    # All 23 scenario IDs, sorted
    all_sids = sorted(set(r["scenario_id"] for r in perf_all + bsr_all),
                      key=lambda s: int(s) if s.isdigit() else 999)

    # FAPI-UL max per scenario
    fapi_max = {}
    for r in perf_all:
        if r["hook_name"] != FAPI_UL_HOOK:
            continue
        sid = r["scenario_id"]
        fapi_max[sid] = max(fapi_max.get(sid, 0), float(r["max_us"]))

    # BSR max (KB) per scenario
    bsr_max_kb = {}
    for r in bsr_all:
        sid = r["scenario_id"]
        bsr_max_kb[sid] = max(bsr_max_kb.get(sid, 0), int(r["bytes"]) / 1024)

    # Baseline values for reference lines
    baseline_fapi = fapi_max.get("00", 0)
    baseline_bsr = bsr_max_kb.get("00", 0)

    fig, axes = plt.subplots(2, 1, figsize=(16, 10))
    fig.suptitle("Stress Anomaly Dataset - Cross-Scenario Summary", fontsize=14, fontweight="bold")

    for ax, title, data, ylabel, baseline_val in [
        (axes[0], f"FAPI-UL ({FAPI_UL_HOOK}) Max Latency", fapi_max, "us", baseline_fapi),
        (axes[1], "BSR Max", bsr_max_kb, "KB", baseline_bsr),
    ]:
        sids_ordered = [s for s in all_sids if s in data]
        vals = [data[s] for s in sids_ordered]
        colors = [STRESS_COLORS.get(meta.get(s, ("", "unknown"))[1], "gray") for s in sids_ordered]
        labels = [f"{s}\n{meta.get(s, ('',''))[0][:18]}" for s in sids_ordered]

        ax.bar(labels, vals, color=colors, edgecolor="black", linewidth=0.5)
        ax.set_title(title, fontsize=11)
        ax.set_ylabel(ylabel)
        if any(v > 0 for v in vals):
            ax.set_yscale("log")
        ax.tick_params(axis="x", labelsize=7, rotation=45)

        # Baseline reference line
        if baseline_val > 0:
            ax.axhline(y=baseline_val, color="steelblue", linestyle="--", linewidth=1.2,
                        label=f"Baseline: {baseline_val:.1f}")
            ax.legend(fontsize=9)

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, edgecolor="black", label=cat)
                       for cat, c in STRESS_COLORS.items()]
    fig.legend(handles=legend_elements, loc="lower center", ncol=6, fontsize=9,
               bbox_to_anchor=(0.5, -0.02))

    plt.tight_layout(rect=[0, 0.04, 1, 0.96])
    out = plots_dir / "stress_summary.png"
    fig.savefig(str(out), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def main():
    print("Generating cross-scenario summaries...\n")
    channel_summary()
    stress_summary()
    print("\nDone.")


if __name__ == "__main__":
    main()
