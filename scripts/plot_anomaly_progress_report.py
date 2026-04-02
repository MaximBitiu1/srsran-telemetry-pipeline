#!/usr/bin/env python3
"""Generate figures for the Anomalous Data Collection Progress Report."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import os

OUT = os.path.expanduser("~/Desktop/anomaly_report_figures")
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
})

# ── Data ────────────────────────────────────────────────────────────────────

# Channel dataset (7 scenarios with full MAC data)
ch_scenarios = ["B1", "B2", "T1", "T2", "S1", "S2", "L1"]
ch_mcs       = [27.6, 15.7, 11.6, 12.0, 22.0, 27.6, 27.5]
ch_bsr_mb    = [1.99, 6.53, 61.6, 0.004, 37.6, 2.01, 12.95]
ch_rlc_ms    = [37, 1853, 1229, 13, 1856, 43, 4072]
ch_harq      = [0.00, 4.14, 1.02, 0.64, 2.93, 0.00, 1.46]
ch_cat       = ["baseline", "baseline", "time_varying", "time_varying",
                "steady", "steady", "rlf"]

cat_colors = {"baseline": "#2ca02c", "time_varying": "#ff7f0e",
              "steady": "#d62728", "rlf": "#9467bd"}
ch_colors = [cat_colors[c] for c in ch_cat]

# Hook latency p99 across channel scenarios
ch_hook_p99 = {"B1": 3.1, "B2": 4.7, "T1": 5.3, "S1": 3.9, "S2": 3.3, "L1": 3.2}

# Stress dataset
st_labels = ["baseline", "cpu_95pct", "mem_balloon",
             "sched_batch", "sched_other", "sched+cpu",
             "combined_dem", "traffic_100M", "traffic_150M"]
st_hook_max = [70.7, 33, 70, 7289, 3617, 2911, 2430, 62, 42]
st_bsr_kb   = [2096, 2343, 9570, 6478, 7565, 16050, 38386, 32129, 32813]
st_cat      = ["grey", "grey", "grey", "red", "red", "red",
               "purple", "orange", "orange"]
st_color_map = {"grey": "#999999", "red": "#d62728",
                "orange": "#ff7f0e", "purple": "#9467bd"}
st_colors = [st_color_map[c] for c in st_cat]

# ── Fig 1: Channel scenario comparison (2x2) ───────────────────────────────

fig, axes = plt.subplots(2, 2, figsize=(10, 6))
x = np.arange(len(ch_scenarios))

# Top-left: MCS
ax = axes[0, 0]
ax.bar(x, ch_mcs, color=ch_colors, edgecolor="black", linewidth=0.5)
ax.set_xticks(x); ax.set_xticklabels(ch_scenarios)
ax.set_ylabel("MCS (avg)"); ax.set_title("Average MCS Index")
ax.set_ylim(0, 30)

# Top-right: BSR max (log)
ax = axes[0, 1]
ax.bar(x, ch_bsr_mb, color=ch_colors, edgecolor="black", linewidth=0.5)
ax.set_xticks(x); ax.set_xticklabels(ch_scenarios)
ax.set_ylabel("BSR max (MB)"); ax.set_title("Peak BSR")
ax.set_yscale("log")
ax.set_ylim(1e-3, 200)

# Bottom-left: RLC delay max (log)
ax = axes[1, 0]
ax.bar(x, ch_rlc_ms, color=ch_colors, edgecolor="black", linewidth=0.5)
ax.set_xticks(x); ax.set_xticklabels(ch_scenarios)
ax.set_ylabel("RLC delay max (ms)"); ax.set_title("Peak RLC Queuing Delay")
ax.set_yscale("log")
ax.set_ylim(1, 10000)

# Bottom-right: HARQ fail/s
ax = axes[1, 1]
ax.bar(x, ch_harq, color=ch_colors, edgecolor="black", linewidth=0.5)
ax.set_xticks(x); ax.set_xticklabels(ch_scenarios)
ax.set_ylabel("HARQ failures/s"); ax.set_title("HARQ Failure Rate")
ax.set_ylim(0, 5)

# Legend
from matplotlib.patches import Patch
legend_elements = [Patch(facecolor=cat_colors[k], edgecolor="black",
                         linewidth=0.5, label=k.replace("_", " ").title())
                   for k in ["baseline", "time_varying", "steady", "rlf"]]
fig.legend(handles=legend_elements, loc="upper center", ncol=4,
           frameon=False, fontsize=9, bbox_to_anchor=(0.5, 1.02))

fig.tight_layout(rect=[0, 0, 1, 0.95])
fig.savefig(f"{OUT}/fig1_channel_comparison.png", dpi=150,
            bbox_inches="tight")
plt.close(fig)
print("Saved fig1_channel_comparison.png")


# ── Fig 2: Stress hook latency (grouped bar) ───────────────────────────────

fig, ax = plt.subplots(figsize=(10, 5))
x = np.arange(len(st_labels))
bars = ax.bar(x, st_hook_max, color=st_colors, edgecolor="black",
              linewidth=0.5)
ax.axhline(70.7, color="black", linestyle="--", linewidth=1, label="Baseline (70.7 us)")
ax.set_yscale("log")
ax.set_xticks(x)
ax.set_xticklabels(st_labels, rotation=35, ha="right")
ax.set_ylabel("FAPI-UL Hook Max Latency (us)")
ax.set_title("Infrastructure Stress: Hook Latency by Scenario")
ax.set_ylim(10, 15000)

# Value labels on top of bars
for bar, val in zip(bars, st_hook_max):
    if val > 200:
        ax.text(bar.get_x() + bar.get_width() / 2, val * 1.15,
                f"{val:.0f}", ha="center", va="bottom", fontsize=8,
                fontweight="bold")

legend_el = [Patch(facecolor="#999999", edgecolor="black", linewidth=0.5,
                   label="No effect (CPU/mem)"),
             Patch(facecolor="#d62728", edgecolor="black", linewidth=0.5,
                   label="Scheduler demotion"),
             Patch(facecolor="#ff7f0e", edgecolor="black", linewidth=0.5,
                   label="Traffic flood"),
             Patch(facecolor="#9467bd", edgecolor="black", linewidth=0.5,
                   label="Combined")]
ax.legend(handles=legend_el, loc="upper left", fontsize=9, framealpha=0.9)

fig.tight_layout()
fig.savefig(f"{OUT}/fig2_stress_hook_latency.png", dpi=150,
            bbox_inches="tight")
plt.close(fig)
print("Saved fig2_stress_hook_latency.png")


# ── Fig 3: Hook latency vs BSR scatter (stress) ────────────────────────────

fig, ax = plt.subplots(figsize=(8, 6))
for i, (lbl, hk, bsr, col) in enumerate(
        zip(st_labels, st_hook_max, st_bsr_kb, st_colors)):
    ax.scatter(bsr, hk, c=col, s=100, edgecolors="black", linewidths=0.5,
               zorder=3)

# Annotate extreme points
annotate_idx = {0: "baseline", 3: "sched_batch", 6: "combined_dem", 7: "traffic_100M"}
offsets = {0: (-15, 15), 3: (15, 15), 6: (15, -20), 7: (15, 15)}
for idx, name in annotate_idx.items():
    ax.annotate(name, (st_bsr_kb[idx], st_hook_max[idx]),
                textcoords="offset points", xytext=offsets[idx],
                fontsize=8, fontstyle="italic",
                arrowprops=dict(arrowstyle="->", color="grey", lw=0.8))

ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("BSR max (KB)"); ax.set_ylabel("FAPI-UL Hook Max Latency (us)")
ax.set_title("Anomaly Signal Space: Hook Latency vs BSR")

# Quadrant annotations
ax.axhline(70.7, color="black", linestyle=":", linewidth=0.8, alpha=0.5)
ax.axvline(10000, color="black", linestyle=":", linewidth=0.8, alpha=0.5)
ax.text(1500, 5000, "Scheduler\nanomaly", fontsize=9, color="#d62728",
        ha="center", fontstyle="italic", alpha=0.7)
ax.text(35000, 30, "Traffic\nanomaly", fontsize=9, color="#ff7f0e",
        ha="center", fontstyle="italic", alpha=0.7)

legend_el = [Patch(facecolor="#999999", edgecolor="black", linewidth=0.5,
                   label="No effect"),
             Patch(facecolor="#d62728", edgecolor="black", linewidth=0.5,
                   label="Scheduler"),
             Patch(facecolor="#ff7f0e", edgecolor="black", linewidth=0.5,
                   label="Traffic"),
             Patch(facecolor="#9467bd", edgecolor="black", linewidth=0.5,
                   label="Combined")]
ax.legend(handles=legend_el, loc="center right", fontsize=9)

fig.tight_layout()
fig.savefig(f"{OUT}/fig3_signal_space_scatter.png", dpi=150,
            bbox_inches="tight")
plt.close(fig)
print("Saved fig3_signal_space_scatter.png")


# ── Fig 4: Hook latency — channel vs stress comparison ─────────────────────

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5),
                                gridspec_kw={"width_ratios": [1, 1.3]})

# Left: channel hook p99
ch_names = list(ch_hook_p99.keys())
ch_vals  = list(ch_hook_p99.values())
ch_x = np.arange(len(ch_names))
ch_bar_colors = [cat_colors[ch_cat[ch_scenarios.index(n)]] for n in ch_names]
ax1.bar(ch_x, ch_vals, color=ch_bar_colors, edgecolor="black", linewidth=0.5)
ax1.set_xticks(ch_x); ax1.set_xticklabels(ch_names)
ax1.set_ylabel("FAPI-UL p99 Latency (us)")
ax1.set_title("Channel Scenarios\n(hook latency unaffected)")
ax1.set_ylim(0, 8)
ax1.axhline(3.1, color="black", linestyle="--", linewidth=0.8, alpha=0.5,
            label="B1 baseline (3.1 us)")
ax1.legend(fontsize=8, loc="upper right")

# Right: stress hook max
st_x = np.arange(len(st_labels))
ax2.bar(st_x, st_hook_max, color=st_colors, edgecolor="black", linewidth=0.5)
ax2.set_xticks(st_x); ax2.set_xticklabels(st_labels, rotation=35, ha="right")
ax2.set_ylabel("FAPI-UL Hook Max Latency (us)")
ax2.set_title("Stress Scenarios\n(scheduler demotion = 40-103x spike)")
ax2.set_yscale("log")
ax2.set_ylim(10, 15000)
ax2.axhline(70.7, color="black", linestyle="--", linewidth=0.8, alpha=0.5)

# Add note
fig.text(0.5, -0.02,
         "Channel impairments do not cause hook latency anomalies. "
         "Hook latency is an infrastructure-only signal.",
         ha="center", fontsize=9, fontstyle="italic", color="#555555")

fig.tight_layout()
fig.savefig(f"{OUT}/fig4_hook_channel_vs_stress.png", dpi=150,
            bbox_inches="tight")
plt.close(fig)
print("Saved fig4_hook_channel_vs_stress.png")

print("\nAll figures saved to", OUT)
