#!/usr/bin/env python3
"""Generate per-scenario time-series plots for stress and channel datasets."""

import csv
import os
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STRESS_DIR = Path.home() / "Desktop" / "dataset" / "stress_20260325_204950"
CHANNEL_DIR = Path.home() / "Desktop" / "channel_dataset" / "20260401_180521"

DATASETS = [
    ("stress", STRESS_DIR),
    ("channel", CHANNEL_DIR),
]


def read_csv(path: Path):
    """Read CSV to list of dicts."""
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def group_by_scenario(rows):
    """Group rows by scenario_id -> list of rows."""
    groups = {}
    for r in rows:
        sid = r["scenario_id"]
        groups.setdefault(sid, []).append(r)
    return groups


def plot_full_scenario(sid, label, category, harq_rows, bsr_rows, perf_rows, out_path):
    """3-row subplot: MCS, BSR, FAPI-UL p99."""
    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    fig.suptitle(f"{sid} - {label} ({category})", fontsize=13, fontweight="bold")

    # Row 1: MCS over time (use all harq_stats, compute avg_mcs)
    if harq_rows:
        t = [float(r["relative_s"]) for r in harq_rows]
        mcs = [float(r["avg_mcs"]) for r in harq_rows]
        axes[0].plot(t, mcs, linewidth=0.8, color="steelblue")
        axes[0].set_ylabel("Avg MCS")
        axes[0].set_ylim(bottom=0)
    else:
        axes[0].text(0.5, 0.5, "No harq_stats data", transform=axes[0].transAxes, ha="center")
    axes[0].set_title("MCS (DL)", fontsize=10)

    # Row 2: BSR (KB) over time
    if bsr_rows:
        t = [float(r["relative_s"]) for r in bsr_rows]
        bsr_kb = [int(r["bytes"]) / 1024 for r in bsr_rows]
        axes[1].plot(t, bsr_kb, linewidth=0.8, color="darkorange")
        axes[1].set_ylabel("BSR (KB)")
        axes[1].set_ylim(bottom=0)
    else:
        axes[1].text(0.5, 0.5, "No bsr_stats data", transform=axes[1].transAxes, ha="center")
    axes[1].set_title("Buffer Status Report", fontsize=10)

    # Row 3: FAPI-UL hook p99
    fapi_rows = [r for r in perf_rows if "fapi_ul" in r.get("hook_name", "").lower()
                 or "fapi-ul" in r.get("hook_name", "").lower()
                 or r.get("hook_name", "") == "FAPI-UL"]
    if not fapi_rows:
        # Try to find the most common hook that looks like fapi ul
        hook_names = set(r.get("hook_name", "") for r in perf_rows)
        for h in hook_names:
            if "fapi" in h.lower() and "ul" in h.lower():
                fapi_rows = [r for r in perf_rows if r["hook_name"] == h]
                break
    if not fapi_rows and perf_rows:
        # Just use the hook with most rows
        from collections import Counter
        hook_counts = Counter(r["hook_name"] for r in perf_rows)
        top_hook = hook_counts.most_common(1)[0][0]
        fapi_rows = [r for r in perf_rows if r["hook_name"] == top_hook]

    if fapi_rows:
        t = [float(r["relative_s"]) for r in fapi_rows]
        p99 = [float(r["p99_us"]) for r in fapi_rows]
        axes[2].plot(t, p99, linewidth=0.8, color="crimson")
        axes[2].set_ylabel("p99 (us)")
        hook_label = fapi_rows[0].get("hook_name", "hook")
        axes[2].set_title(f"{hook_label} p99 latency", fontsize=10)
    else:
        axes[2].text(0.5, 0.5, "No perf data", transform=axes[2].transAxes, ha="center")
        axes[2].set_title("Hook p99 latency", fontsize=10)

    axes[2].set_xlabel("Time (s)")
    plt.tight_layout()
    fig.savefig(str(out_path), dpi=150)
    plt.close(fig)


def plot_perf_only(sid, label, category, perf_rows, out_path):
    """Single-row plot of hook p99 over time."""
    # Find FAPI-UL hook
    fapi_rows = [r for r in perf_rows if "fapi" in r.get("hook_name", "").lower()
                 and "ul" in r.get("hook_name", "").lower()]
    if not fapi_rows:
        from collections import Counter
        hook_counts = Counter(r["hook_name"] for r in perf_rows)
        if hook_counts:
            top_hook = hook_counts.most_common(1)[0][0]
            fapi_rows = [r for r in perf_rows if r["hook_name"] == top_hook]

    if not fapi_rows:
        return False

    fig, ax = plt.subplots(figsize=(12, 4))
    t = [float(r["relative_s"]) for r in fapi_rows]
    p99 = [float(r["p99_us"]) for r in fapi_rows]
    ax.plot(t, p99, linewidth=0.8, color="crimson")
    ax.set_ylabel("p99 (us)")
    ax.set_xlabel("Time (s)")
    hook_label = fapi_rows[0].get("hook_name", "hook")
    ax.set_title(f"{sid} - {label} ({category}) | {hook_label} p99", fontsize=12, fontweight="bold")
    plt.tight_layout()
    fig.savefig(str(out_path), dpi=150)
    plt.close(fig)
    return True


def process_dataset(name, base_dir):
    csv_dir = base_dir / "csv"
    plots_dir = base_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    # Load CSVs
    harq_all = read_csv(csv_dir / "harq_stats.csv")
    bsr_all = read_csv(csv_dir / "bsr_stats.csv")
    perf_all = read_csv(csv_dir / "jbpf_out_perf_list.csv")

    harq_by_scen = group_by_scenario(harq_all)
    bsr_by_scen = group_by_scenario(bsr_all)
    perf_by_scen = group_by_scenario(perf_all)

    # Get all scenario IDs
    all_sids = set()
    all_sids.update(harq_by_scen.keys())
    all_sids.update(bsr_by_scen.keys())
    all_sids.update(perf_by_scen.keys())

    plot_count = 0
    for sid in sorted(all_sids):
        harq = harq_by_scen.get(sid, [])
        bsr = bsr_by_scen.get(sid, [])
        perf = perf_by_scen.get(sid, [])

        # Get label and category from first available row
        sample = (harq or bsr or perf)[0] if (harq or bsr or perf) else {}
        label = sample.get("label", sid)
        category = sample.get("category", "unknown")

        has_mac = bool(harq or bsr)

        if has_mac:
            out_path = plots_dir / f"ts_{sid}_{label}.png"
            plot_full_scenario(sid, label, category, harq, bsr, perf, out_path)
            print(f"  [{name}] {out_path.name}")
            plot_count += 1
        elif perf:
            out_path = plots_dir / f"ts_{sid}_{label}.png"
            ok = plot_perf_only(sid, label, category, perf, out_path)
            if ok:
                print(f"  [{name}] {out_path.name} (perf only)")
                plot_count += 1

    return plot_count


def main():
    total = 0
    for name, base_dir in DATASETS:
        print(f"\n--- {name} dataset ---")
        count = process_dataset(name, base_dir)
        print(f"  Generated {count} plots")
        total += count

    print(f"\nTotal plots generated: {total}")


if __name__ == "__main__":
    main()
