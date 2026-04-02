#!/usr/bin/env python3
"""
Plot channel scenarios collected on 2026-04-02.
Produces:
  - datasets/channel/plots/ts_today_<ID>_<label>.png  (one per scenario)
  - datasets/channel/plots/today_channel_overview.png  (combined multi-panel)
"""

import csv
import os
from pathlib import Path
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

# ---------------------------------------------------------------------------
REPO_DIR = Path(__file__).resolve().parent.parent
CHANNEL_CSV = REPO_DIR / "datasets" / "channel" / "csv"
PLOTS_DIR   = REPO_DIR / "datasets" / "channel" / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# Scenarios acquired today (2026-04-02)
TODAY_SCENARIOS = ["T1", "T3", "T4", "T5", "S1", "S3", "L2"]

# Channel configuration labels for each scenario
SCENARIO_CONFIG = {
    "T1": "EPA, SNR 20→12 dB, fd 70→200 Hz\n25 Mbps load — UE crashed at 81 s",
    "T3": "EPA, SNR 22 dB ±10, fd 1–20 Hz\n25 Mbps load — UE did not attach",
    "T4": "EPA, SNR 28→12 dB over 60 s\n25 Mbps load — UE did not attach",
    "T5": "EVA, SNR 25 dB, fd 10 Hz\n20 Mbps load — UE did not attach",
    "S1": "EPA, SNR 20 dB, CW SIR 15 dB\n20 Mbps load — UE crashed at 25 s",
    "S3": "EPA, SNR 22 dB, fd 300 Hz, 3% drops\n20 Mbps load — UE did not attach",
    "L2": "EPA, SNR 20 dB, fd 70 Hz\n4 s blackout / 90 s — UE did not attach",
}

# ---------------------------------------------------------------------------

def load_csv(path: Path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def group_by(rows, key="scenario_id"):
    out = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return out

def fapi_ul_rows(perf_rows):
    """Return FAPI-UL hook rows, falling back to most common hook."""
    fapi = [r for r in perf_rows
            if "fapi" in r.get("hook_name","").lower()
            and "ul" in r.get("hook_name","").lower()]
    if fapi:
        return fapi
    from collections import Counter
    if not perf_rows:
        return []
    top = Counter(r["hook_name"] for r in perf_rows).most_common(1)[0][0]
    return [r for r in perf_rows if r["hook_name"] == top]

def plot_mac_scenario(ax_mcs, ax_bsr, ax_hook, sid, label, category, harq, bsr, perf):
    """Fill three axes for a scenario with full MAC data."""
    config = SCENARIO_CONFIG.get(sid, "")
    title = f"{sid} — {label}\n{config}"

    if harq:
        t   = [float(r["relative_s"]) for r in harq]
        mcs = [float(r["avg_mcs"])    for r in harq]
        ax_mcs.plot(t, mcs, lw=0.8, color="steelblue")
        ax_mcs.set_ylim(0, 30)
    else:
        ax_mcs.text(0.5, 0.5, "no MAC data", transform=ax_mcs.transAxes,
                    ha="center", color="grey")
    ax_mcs.set_ylabel("MCS", fontsize=8)
    ax_mcs.set_title(title, fontsize=8, loc="left")
    ax_mcs.tick_params(labelsize=7)

    if bsr:
        t      = [float(r["relative_s"]) for r in bsr]
        bsr_kb = [int(r["bytes"]) / 1024  for r in bsr]
        ax_bsr.plot(t, bsr_kb, lw=0.8, color="darkorange")
        ax_bsr.set_ylim(bottom=0)
    else:
        ax_bsr.text(0.5, 0.5, "no BSR data", transform=ax_bsr.transAxes,
                    ha="center", color="grey")
    ax_bsr.set_ylabel("BSR (KB)", fontsize=8)
    ax_bsr.tick_params(labelsize=7)

    fapi = fapi_ul_rows(perf)
    if fapi:
        t   = [float(r["relative_s"]) for r in fapi]
        p99 = [float(r["p99_us"])     for r in fapi]
        ax_hook.plot(t, p99, lw=0.8, color="crimson")
    else:
        ax_hook.text(0.5, 0.5, "no hook data", transform=ax_hook.transAxes,
                     ha="center", color="grey")
    hook_label = fapi[0]["hook_name"] if fapi else "hook"
    ax_hook.set_ylabel("p99 (µs)", fontsize=8)
    ax_hook.set_xlabel("Time (s)", fontsize=8)
    ax_hook.tick_params(labelsize=7)

def plot_hook_only_scenario(ax, sid, label, category, perf):
    """Fill one axis for a jbpf-only scenario."""
    config = SCENARIO_CONFIG.get(sid, "")
    title = f"{sid} — {label}\n{config}"

    fapi = fapi_ul_rows(perf)
    if fapi:
        # Show only the last 180 s of data (the actual collection window)
        t_all   = np.array([float(r["relative_s"]) for r in fapi])
        p99_all = np.array([float(r["p99_us"])     for r in fapi])
        t_end   = t_all.max()
        mask    = t_all >= max(0, t_end - 185)          # last ~185 s
        t   = t_all[mask]  - (t_end - min(180, t_end))  # re-zero to ~0
        p99 = p99_all[mask]
        ax.plot(t, p99, lw=0.8, color="crimson")
        ax.set_ylim(bottom=0)
        ax.annotate("UE did not attach\n(hook-latency only)",
                    xy=(0.5, 0.75), xycoords="axes fraction",
                    ha="center", fontsize=7, color="grey",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7))
    else:
        ax.text(0.5, 0.5, "no data", transform=ax.transAxes,
                ha="center", color="grey")

    ax.set_title(title, fontsize=8, loc="left")
    ax.set_ylabel("p99 (µs)", fontsize=8)
    ax.set_xlabel("Time (s)", fontsize=8)
    ax.tick_params(labelsize=7)

# ---------------------------------------------------------------------------

def main():
    harq_all = load_csv(CHANNEL_CSV / "harq_stats.csv")
    bsr_all  = load_csv(CHANNEL_CSV / "bsr_stats.csv")
    perf_all = load_csv(CHANNEL_CSV / "jbpf_out_perf_list.csv")

    harq_by = group_by(harq_all)
    bsr_by  = group_by(bsr_all)
    perf_by = group_by(perf_all)

    # -------------------------------------------------------------------
    # 1. Per-scenario individual plots
    # -------------------------------------------------------------------
    for sid in TODAY_SCENARIOS:
        harq = harq_by.get(sid, [])
        bsr  = bsr_by.get(sid,  [])
        perf = perf_by.get(sid, [])

        sample   = (harq or bsr or perf)[0] if (harq or bsr or perf) else {}
        label    = sample.get("label",    sid)
        category = sample.get("category", "unknown")
        config   = SCENARIO_CONFIG.get(sid, "")

        has_mac = bool(harq or bsr)

        if has_mac:
            fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
            fig.suptitle(f"{sid} — {label}  ({category})\n{config}",
                         fontsize=10, fontweight="bold")
            plot_mac_scenario(axes[0], axes[1], axes[2],
                              sid, label, category, harq, bsr, perf)
        else:
            fig, ax = plt.subplots(figsize=(11, 3.5))
            plot_hook_only_scenario(ax, sid, label, category, perf)
            fig.suptitle(f"{sid} — {label}  ({category})",
                         fontsize=10, fontweight="bold")

        plt.tight_layout()
        out = PLOTS_DIR / f"ts_today_{sid}_{label}.png"
        fig.savefig(str(out), dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  Saved {out.name}")

    # -------------------------------------------------------------------
    # 2. Combined overview figure (7 scenarios in a grid)
    # -------------------------------------------------------------------
    # Layout: MAC scenarios (T1, S1) get 3 rows each; hook-only get 1 row each
    # Arrange: 2 MAC scenarios side-by-side (top), then 5 hook-only in a row below
    mac_ids  = [s for s in TODAY_SCENARIOS if harq_by.get(s) or bsr_by.get(s)]
    hook_ids = [s for s in TODAY_SCENARIOS if s not in mac_ids]

    fig = plt.figure(figsize=(16, 11))
    fig.suptitle("Realistic Channel Scenarios — Collected 2026-04-02",
                 fontsize=13, fontweight="bold", y=0.99)

    # Top section: MAC scenarios (each 3 subplots high)
    n_mac = len(mac_ids)
    n_hook = len(hook_ids)

    outer = gridspec.GridSpec(2, 1, figure=fig,
                              height_ratios=[3, 1.2], hspace=0.45)

    # Top row: MAC scenarios side by side
    top_gs = gridspec.GridSpecFromSubplotSpec(3, max(n_mac, 1),
                                              subplot_spec=outer[0],
                                              hspace=0.08, wspace=0.35)
    for col, sid in enumerate(mac_ids):
        harq = harq_by.get(sid, [])
        bsr  = bsr_by.get(sid,  [])
        perf = perf_by.get(sid, [])
        sample   = (harq or bsr or perf)[0] if (harq or bsr or perf) else {}
        label    = sample.get("label",    sid)
        category = sample.get("category", "unknown")

        ax_mcs  = fig.add_subplot(top_gs[0, col])
        ax_bsr  = fig.add_subplot(top_gs[1, col], sharex=ax_mcs)
        ax_hook = fig.add_subplot(top_gs[2, col], sharex=ax_mcs)
        plt.setp(ax_mcs.get_xticklabels(),  visible=False)
        plt.setp(ax_bsr.get_xticklabels(),  visible=False)
        plot_mac_scenario(ax_mcs, ax_bsr, ax_hook,
                          sid, label, category, harq, bsr, perf)

    # Bottom row: hook-only scenarios
    bot_gs = gridspec.GridSpecFromSubplotSpec(1, max(n_hook, 1),
                                              subplot_spec=outer[1],
                                              hspace=0.08, wspace=0.35)
    for col, sid in enumerate(hook_ids):
        perf   = perf_by.get(sid, [])
        sample = perf[0] if perf else {}
        label    = sample.get("label",    sid)
        category = sample.get("category", "unknown")
        ax = fig.add_subplot(bot_gs[0, col])
        plot_hook_only_scenario(ax, sid, label, category, perf)

    out_combined = PLOTS_DIR / "today_channel_overview.png"
    fig.savefig(str(out_combined), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Saved combined overview: {out_combined.name}")

    print(f"\nDone. All plots in {PLOTS_DIR}")


if __name__ == "__main__":
    main()
