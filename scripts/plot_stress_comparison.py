#!/usr/bin/env python3
"""
Stress Anomaly Cross-Scenario Comparison Plots
===============================================
Loads all scenario logs from a dataset directory and generates:
  1. Hook latency comparison (fapi_ul max, p99 across scenarios)
  2. BSR buffer bytes comparison
  3. HARQ failures + SINR comparison
  4. Normalised anomaly heatmap (all metrics, all scenarios)
  5. Time-series overlay for selected hooks (top-N anomalous scenarios)
  6. Per-category latency distribution box plots

Usage:
    python3 plot_stress_comparison.py [dataset_dir]

    Default: ~/Desktop/dataset/  (most recent run found automatically)
"""
import json, re, os, sys, glob
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.cm as cm
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────────
if len(sys.argv) > 1:
    DATASET_DIR = Path(sys.argv[1])
else:
    base = Path.home() / "Desktop" / "dataset"
    candidates = sorted(base.glob("stress_*"), reverse=True)
    if not candidates:
        print("ERROR: No stress_* dataset directories found under ~/Desktop/dataset/")
        sys.exit(1)
    DATASET_DIR = candidates[0]

OUT_DIR = DATASET_DIR / "plots"
OUT_DIR.mkdir(exist_ok=True)
print(f"Dataset : {DATASET_DIR}")
print(f"Plots → : {OUT_DIR}")

# ── Style ─────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "#F7F9FC",
    "axes.grid": True,
    "grid.alpha": 0.4,
    "grid.linestyle": "--",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "legend.fontsize": 8,
    "figure.dpi": 150,
})

CATEGORY_COLORS = {
    "baseline": "#2196F3",
    "cpu":      "#FF5722",
    "memory":   "#9C27B0",
    "sched":    "#F44336",
    "traffic":  "#4CAF50",
    "combined": "#FF9800",
}

# ── Parser ────────────────────────────────────────────────────────────────────
def parse_log(path):
    """Return dict of schema → list of records (with _ts added)."""
    records = defaultdict(list)
    with open(path, errors='replace') as f:
        for line in f:
            m = re.match(r'^time="([^"]+)".*msg="REC: (.+)"$', line.strip())
            if not m:
                continue
            ts_str, raw = m.group(1), m.group(2)
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                continue
            raw = raw.replace('\\"', '"')
            if raw.startswith('"'): raw = raw[1:]
            if raw.endswith('"'):   raw = raw[:-1]
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            schema = data.get("_schema_proto_msg", "unknown")
            pkg = data.get("_schema_proto_package", "")
            if schema == "crc_stats" and pkg == "fapi_gnb_crc_stats":
                schema = "fapi_crc_stats"
            data["_ts"] = ts
            records[schema].append(data)
    return records

def safe_div(a, b, default=0.0):
    return a / b if b else default

# ── Collect scenario files ────────────────────────────────────────────────────
log_files = sorted(DATASET_DIR.rglob("*.log"))
if not log_files:
    print("ERROR: No .log files found")
    sys.exit(1)
print(f"Found {len(log_files)} scenario logs")

# ── Extract summary metrics from each log ────────────────────────────────────
def extract_metrics(records):
    """Return a flat dict of summary metrics for one scenario."""
    m = {}

    # ── jbpf hook perf ───────────────────────────────────────────────────────
    perf_recs = records.get("jbpf_out_perf_list", [])
    # Aggregate per hookName across all time windows (take max of max, median of p50)
    hook_agg = defaultdict(lambda: {"max_vals": [], "p50_vals": [], "p99_vals": [], "num_vals": []})
    for r in perf_recs:
        for h in r.get("hookPerf", []):
            name = h.get("hookName", "")
            hook_agg[name]["max_vals"].append(int(h.get("max", 0)))
            hook_agg[name]["p50_vals"].append(int(h.get("p50", 0)))
            hook_agg[name]["p99_vals"].append(int(h.get("p99", 0)))
            hook_agg[name]["num_vals"].append(int(h.get("num", 0)))

    for hook_name, agg in hook_agg.items():
        key = hook_name.replace("_", ".")
        if agg["max_vals"]:
            m[f"hook.{key}.max"]    = max(agg["max_vals"])
            m[f"hook.{key}.p99"]    = max(agg["p99_vals"])
            m[f"hook.{key}.p50_med"] = float(np.median(agg["p50_vals"]))
            m[f"hook.{key}.total_events"] = sum(agg["num_vals"])

    # ── BSR stats ────────────────────────────────────────────────────────────
    # BSR duUeIndex is 0 for the real UE — no ghost filter needed here
    bsr_recs = records.get("bsr_stats", [])
    bsr_bytes = []
    for r in bsr_recs:
        for s in r.get("stats", []):
            bsr_bytes.append(int(s.get("bytes", 0)))
    if bsr_bytes:
        m["bsr.bytes.max"]    = max(bsr_bytes)
        m["bsr.bytes.p95"]    = float(np.percentile(bsr_bytes, 95))
        m["bsr.bytes.median"] = float(np.median(bsr_bytes))

    # ── MAC CRC / HARQ ───────────────────────────────────────────────────────
    # Real UE is always duUeIndex=0; duUeIndex=513 is a ghost scheduler entry
    crc_recs = records.get("crc_stats", [])
    harq_failures = []
    sinr_vals = []
    for r in crc_recs:
        for s in r.get("stats", []):
            if s.get("duUeIndex", 0) == 513: continue  # exclude ghost
            harq_failures.append(s.get("harqFailure", 0))
            cnt = s.get("cntSinr", 0)
            sumv = s.get("sumSinr", 0)
            if cnt > 0:
                sinr_vals.append(safe_div(sumv, cnt))
    if harq_failures:
        m["harq.failures.total"] = sum(harq_failures)
        m["harq.failures.max"]   = max(harq_failures)
    if sinr_vals:
        m["sinr.avg"] = float(np.mean(sinr_vals))
        m["sinr.min"] = float(np.min(sinr_vals))

    # ── HARQ stats (retx) ────────────────────────────────────────────────────
    harq_recs = records.get("harq_stats", [])
    retx_vals = []
    for r in harq_recs:
        for s in r.get("stats", []):
            if s.get("duUeIndex", 0) == 513: continue  # exclude ghost
            retx_vals.append(s.get("nofRetxs", 0))
    if retx_vals:
        m["harq.retx.total"] = sum(retx_vals)

    # ── RLC UL stats ─────────────────────────────────────────────────────────
    rlc_recs = records.get("rlc_ul_stats", [])
    rlc_delays = []
    for r in rlc_recs:
        for s in r.get("stats", []):
            if s.get("duUeIndex", 0) == 513: continue  # exclude ghost
            d = s.get("sduDelay", {})
            if isinstance(d, dict) and d.get("count", 0) > 0:
                rlc_delays.append(safe_div(int(d.get("sum", 0)), d.get("count", 0)))
    if rlc_delays:
        m["rlc_ul.delay_avg_ns"] = float(np.mean(rlc_delays))
        m["rlc_ul.delay_max_ns"] = max(rlc_delays)

    return m

# ── Load all scenarios ────────────────────────────────────────────────────────
scenarios = []
for lf in log_files:
    parts = lf.stem.split("_", 1)
    sid = parts[0]
    label = lf.stem
    category = lf.parent.name  # subfolder = category
    print(f"  Parsing {lf.name} ...", end=" ", flush=True)
    recs = parse_log(lf)
    total = sum(len(v) for v in recs.values())
    metrics = extract_metrics(recs)
    print(f"{total} records, {len(metrics)} metrics")
    scenarios.append({
        "id": sid,
        "label": label,
        "category": category,
        "path": lf,
        "records": recs,
        "metrics": metrics,
    })

scenarios.sort(key=lambda s: s["id"])

labels     = [s["label"] for s in scenarios]
categories = [s["category"] for s in scenarios]
colors     = [CATEGORY_COLORS.get(c, "#607D8B") for c in categories]
N = len(scenarios)
x = np.arange(N)

def short_label(lbl):
    """Strip leading NN_ from label for display."""
    return re.sub(r'^\d+_', '', lbl)

xlabels = [short_label(l) for l in labels]

# ── Legend patches ────────────────────────────────────────────────────────────
legend_patches = [mpatches.Patch(color=v, label=k) for k, v in CATEGORY_COLORS.items()
                  if k in set(categories)]

# =============================================================================
# Figure 1 — FAPI UL TTI Hook Latency (max across run)
# =============================================================================
print("\nPlotting Figure 1: FAPI hook latency ...")

fig, axs = plt.subplots(2, 1, figsize=(16, 10))
fig.suptitle("jBPF Hook Processing Latency — Scenario Comparison", fontsize=14, fontweight="bold")

ul_max = [s["metrics"].get("hook.fapi_ul_tti_request.max", 0) / 1000 for s in scenarios]
dl_max = [s["metrics"].get("hook.fapi_dl_tti_request.max", 0) / 1000 for s in scenarios]
ul_p99 = [s["metrics"].get("hook.fapi_ul_tti_request.p99", 0) / 1000 for s in scenarios]

bars = axs[0].bar(x, ul_max, color=colors, edgecolor="white", linewidth=0.5, zorder=3)
axs[0].axhline(ul_max[0], color="black", ls="--", lw=1.2, label=f"Baseline ({ul_max[0]:.1f} µs)")
axs[0].set_ylabel("Max Latency (µs)")
axs[0].set_title("FAPI UL TTI Request Hook — Peak Latency per Scenario")
axs[0].set_xticks(x)
axs[0].set_xticklabels(xlabels, rotation=55, ha="right", fontsize=8)
axs[0].legend(handles=legend_patches + [mpatches.Patch(color="none", label="")], loc="upper left", ncol=3)
# Annotate bars > 2× baseline
for i, v in enumerate(ul_max):
    if v > ul_max[0] * 2 and v > 0:
        axs[0].text(i, v + ul_max[0]*0.1, f"{v:.0f}", ha="center", va="bottom", fontsize=7, fontweight="bold", color="red")

bars2 = axs[1].bar(x, ul_p99, color=colors, edgecolor="white", linewidth=0.5, zorder=3)
axs[1].axhline(ul_p99[0], color="black", ls="--", lw=1.2, label=f"Baseline ({ul_p99[0]:.1f} µs)")
axs[1].set_ylabel("p99 Latency (µs)")
axs[1].set_title("FAPI UL TTI Request Hook — p99 Latency per Scenario")
axs[1].set_xticks(x)
axs[1].set_xticklabels(xlabels, rotation=55, ha="right", fontsize=8)
axs[1].legend(handles=legend_patches, loc="upper left", ncol=3)
for i, v in enumerate(ul_p99):
    if v > ul_p99[0] * 2 and v > 0:
        axs[1].text(i, v + ul_p99[0]*0.1, f"{v:.0f}", ha="center", va="bottom", fontsize=7, fontweight="bold", color="red")

plt.tight_layout()
out1 = OUT_DIR / "01_hook_latency_comparison.png"
plt.savefig(out1, dpi=150, bbox_inches="tight")
plt.close()
print(f"  -> {out1.name}")

# =============================================================================
# Figure 2 — BSR Buffer Bytes
# =============================================================================
print("Plotting Figure 2: BSR buffer bytes ...")

fig, axs = plt.subplots(2, 1, figsize=(16, 10))
fig.suptitle("MAC BSR Buffer Status — Scenario Comparison", fontsize=14, fontweight="bold")

bsr_max    = [s["metrics"].get("bsr.bytes.max", 0) / 1024 for s in scenarios]
bsr_median = [s["metrics"].get("bsr.bytes.median", 0) / 1024 for s in scenarios]

axs[0].bar(x, bsr_max, color=colors, edgecolor="white", linewidth=0.5, zorder=3)
axs[0].axhline(bsr_max[0], color="black", ls="--", lw=1.2, label=f"Baseline ({bsr_max[0]:.0f} KB)")
axs[0].set_ylabel("Buffer Bytes (KB)")
axs[0].set_title("BSR Peak Buffer Size per Scenario")
axs[0].set_xticks(x)
axs[0].set_xticklabels(xlabels, rotation=55, ha="right", fontsize=8)
axs[0].legend(handles=legend_patches, loc="upper left", ncol=3)
for i, v in enumerate(bsr_max):
    if v > bsr_max[0] * 5 and v > 0:
        axs[0].text(i, v, f"{v:.0f}KB", ha="center", va="bottom", fontsize=7, fontweight="bold", color="darkgreen")

axs[1].bar(x, bsr_median, color=colors, edgecolor="white", linewidth=0.5, zorder=3)
axs[1].axhline(bsr_median[0], color="black", ls="--", lw=1.2, label=f"Baseline ({bsr_median[0]:.0f} KB)")
axs[1].set_ylabel("Buffer Bytes (KB)")
axs[1].set_title("BSR Median Buffer Size per Scenario")
axs[1].set_xticks(x)
axs[1].set_xticklabels(xlabels, rotation=55, ha="right", fontsize=8)
axs[1].legend(handles=legend_patches, loc="upper left", ncol=3)

plt.tight_layout()
out2 = OUT_DIR / "02_bsr_comparison.png"
plt.savefig(out2, dpi=150, bbox_inches="tight")
plt.close()
print(f"  -> {out2.name}")

# =============================================================================
# Figure 3 — HARQ Failures + SINR
# =============================================================================
print("Plotting Figure 3: HARQ + SINR ...")

fig, axs = plt.subplots(2, 1, figsize=(16, 10))
fig.suptitle("MAC CRC: HARQ Failures & SINR — Scenario Comparison", fontsize=14, fontweight="bold")

harq_total = [s["metrics"].get("harq.failures.total", 0) for s in scenarios]
sinr_avg   = [s["metrics"].get("sinr.avg", 0) for s in scenarios]

axs[0].bar(x, harq_total, color=colors, edgecolor="white", linewidth=0.5, zorder=3)
axs[0].set_ylabel("Total HARQ Failures")
axs[0].set_title("HARQ Failure Count per Scenario")
axs[0].set_xticks(x)
axs[0].set_xticklabels(xlabels, rotation=55, ha="right", fontsize=8)
axs[0].legend(handles=legend_patches, loc="upper left", ncol=3)

axs[1].bar(x, sinr_avg, color=colors, edgecolor="white", linewidth=0.5, zorder=3)
if sinr_avg[0]:
    axs[1].axhline(sinr_avg[0], color="black", ls="--", lw=1.2, label=f"Baseline ({sinr_avg[0]:.1f} dB)")
axs[1].set_ylabel("Avg SINR (dB)")
axs[1].set_title("Average SINR per Scenario")
axs[1].set_xticks(x)
axs[1].set_xticklabels(xlabels, rotation=55, ha="right", fontsize=8)
axs[1].legend(handles=legend_patches, loc="upper left", ncol=3)

plt.tight_layout()
out3 = OUT_DIR / "03_harq_sinr_comparison.png"
plt.savefig(out3, dpi=150, bbox_inches="tight")
plt.close()
print(f"  -> {out3.name}")

# =============================================================================
# Figure 4 — Normalised Anomaly Heatmap
# =============================================================================
print("Plotting Figure 4: Anomaly heatmap ...")

METRIC_COLS = [
    ("hook.fapi_ul_tti_request.max",       "FAPI-UL hook max (ns)"),
    ("hook.fapi_ul_tti_request.p99",       "FAPI-UL hook p99 (ns)"),
    ("hook.fapi_dl_tti_request.max",       "FAPI-DL hook max (ns)"),
    ("hook.rlc_ul_sdu_delivered.max",      "RLC-UL sdu_delivered max (ns)"),
    ("hook.rlc_ul_rx_pdu.max",             "RLC-UL rx_pdu max (ns)"),
    ("hook.pdcp_ul_deliver_sdu.max",       "PDCP-UL deliver_sdu max (ns)"),
    ("bsr.bytes.max",                      "BSR max bytes"),
    ("bsr.bytes.p95",                      "BSR p95 bytes"),
    ("harq.failures.total",                "HARQ failures total"),
    ("sinr.avg",                           "Avg SINR (dB)"),
]

heat_data = np.zeros((N, len(METRIC_COLS)))
for i, sc in enumerate(scenarios):
    for j, (key, _) in enumerate(METRIC_COLS):
        heat_data[i, j] = sc["metrics"].get(key, 0.0)

# Normalise each column 0..1 (min–max); for SINR invert (lower = worse)
heat_norm = np.zeros_like(heat_data)
for j, (key, _) in enumerate(METRIC_COLS):
    col = heat_data[:, j]
    cmin, cmax = col.min(), col.max()
    if cmax > cmin:
        heat_norm[:, j] = (col - cmin) / (cmax - cmin)
    if "sinr" in key.lower():
        heat_norm[:, j] = 1.0 - heat_norm[:, j]  # invert SINR

fig, ax = plt.subplots(figsize=(14, max(8, N * 0.38)))
im = ax.imshow(heat_norm, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=1)

ax.set_xticks(range(len(METRIC_COLS)))
ax.set_xticklabels([c[1] for c in METRIC_COLS], rotation=40, ha="right", fontsize=9)
ax.set_yticks(range(N))
ax.set_yticklabels(xlabels, fontsize=9)

# Colour y-tick labels by category
for tick, sc in zip(ax.get_yticklabels(), scenarios):
    tick.set_color(CATEGORY_COLORS.get(sc["category"], "#000000"))

# Annotate cells with raw values
for i in range(N):
    for j in range(len(METRIC_COLS)):
        v = heat_data[i, j]
        if v >= 1e6:
            txt = f"{v/1e6:.1f}M"
        elif v >= 1e3:
            txt = f"{v/1e3:.0f}K"
        else:
            txt = f"{v:.0f}"
        ax.text(j, i, txt, ha="center", va="center",
                fontsize=7, color="black" if heat_norm[i, j] < 0.85 else "white")

plt.colorbar(im, ax=ax, shrink=0.6, label="Normalised anomaly score (1 = most anomalous)")
ax.set_title("Normalised Anomaly Heatmap — All Scenarios × All Metrics\n"
             "(y-axis colour = category)", fontsize=12, fontweight="bold", pad=12)

# Category legend
for cat, col in CATEGORY_COLORS.items():
    if cat in set(categories):
        ax.plot([], [], "s", color=col, label=cat, markersize=9)
ax.legend(loc="upper right", bbox_to_anchor=(1.18, 1.0), title="Category", fontsize=8, title_fontsize=9)

plt.tight_layout()
out4 = OUT_DIR / "04_anomaly_heatmap.png"
plt.savefig(out4, dpi=150, bbox_inches="tight")
plt.close()
print(f"  -> {out4.name}")

# =============================================================================
# Figure 5 — Time-series overlay: FAPI-UL hook max over time
#            (top-6 most anomalous scenarios + baseline)
# =============================================================================
print("Plotting Figure 5: Time-series hook latency overlay ...")

# Rank scenarios by fapi_ul max, pick top 6 (excluding baseline)
ranked = sorted(scenarios[1:], key=lambda s: s["metrics"].get("hook.fapi_ul_tti_request.max", 0), reverse=True)
selected = [scenarios[0]] + ranked[:6]  # baseline + top-6

fig, axs = plt.subplots(2, 1, figsize=(15, 10), sharex=False)
fig.suptitle("FAPI UL TTI Hook Latency Over Time — Baseline vs Top-6 Anomalous",
             fontsize=13, fontweight="bold")

ts_colors = plt.cm.tab10(np.linspace(0, 1, len(selected)))

for ax_i, ax in enumerate(axs):
    hook_name = "fapi_ul_tti_request" if ax_i == 0 else "fapi_dl_tti_request"
    title_sfx = "UL" if ax_i == 0 else "DL"

    for idx, sc in enumerate(selected):
        perf_recs = sc["records"].get("jbpf_out_perf_list", [])
        if not perf_recs:
            continue
        t0 = perf_recs[0]["_ts"]
        ts_list, val_list = [], []
        for r in perf_recs:
            for h in r.get("hookPerf", []):
                if h.get("hookName") == hook_name:
                    t_sec = (r["_ts"] - t0).total_seconds()
                    ts_list.append(t_sec)
                    val_list.append(int(h.get("max", 0)) / 1000)  # → µs
                    break
        if ts_list:
            lw = 2.5 if sc["category"] == "baseline" else 1.5
            ls = "--" if sc["category"] == "baseline" else "-"
            ax.plot(ts_list, val_list, color=ts_colors[idx], lw=lw, ls=ls,
                    label=short_label(sc["label"]), alpha=0.85)

    ax.set_ylabel("Hook max latency (µs)")
    ax.set_xlabel("Time (seconds)")
    ax.set_title(f"FAPI {title_sfx} TTI Request — Peak Latency per Measurement Window")
    ax.legend(loc="upper right", ncol=2, fontsize=8)

plt.tight_layout()
out5 = OUT_DIR / "05_timeseries_overlay.png"
plt.savefig(out5, dpi=150, bbox_inches="tight")
plt.close()
print(f"  -> {out5.name}")

# =============================================================================
# Figure 6 — Multi-hook latency grouped bar chart (max)
# =============================================================================
print("Plotting Figure 6: Multi-hook grouped bar chart ...")

HOOKS_OF_INTEREST = [
    ("fapi_ul_tti_request",  "FAPI-UL TTI"),
    ("fapi_dl_tti_request",  "FAPI-DL TTI"),
    ("rlc_ul_sdu_delivered", "RLC-UL SDU"),
    ("rlc_ul_rx_pdu",        "RLC-UL RX"),
    ("pdcp_ul_deliver_sdu",  "PDCP-UL SDU"),
]

n_hooks = len(HOOKS_OF_INTEREST)
width = 0.8 / n_hooks
offsets = np.linspace(-(n_hooks - 1) * width / 2, (n_hooks - 1) * width / 2, n_hooks)
hook_colors = plt.cm.Set2(np.linspace(0, 1, n_hooks))

fig, ax = plt.subplots(figsize=(18, 7))
ax.set_title("Per-Hook Max Latency — All Scenarios (grouped by hook)", fontsize=13, fontweight="bold")

for hi, ((hook_key, hook_lbl), off) in enumerate(zip(HOOKS_OF_INTEREST, offsets)):
    vals = [s["metrics"].get(f"hook.{hook_key}.max", 0) / 1000 for s in scenarios]
    ax.bar(x + off, vals, width=width, color=hook_colors[hi], label=hook_lbl, edgecolor="white", linewidth=0.3)

ax.set_xticks(x)
ax.set_xticklabels(xlabels, rotation=55, ha="right", fontsize=8)
ax.set_ylabel("Max Latency (µs)")
ax.legend(loc="upper left", ncol=n_hooks)

# Category background shading
cat_order = []
for i, sc in enumerate(scenarios):
    if not cat_order or cat_order[-1][0] != sc["category"]:
        cat_order.append((sc["category"], i))
for ci, (cat, start) in enumerate(cat_order):
    end = cat_order[ci + 1][1] if ci + 1 < len(cat_order) else N
    ax.axvspan(start - 0.5, end - 0.5, alpha=0.06,
               color=CATEGORY_COLORS.get(cat, "#607D8B"), zorder=0)
    ax.text((start + end - 1) / 2, ax.get_ylim()[1] * 0.97, cat,
            ha="center", va="top", fontsize=8, color=CATEGORY_COLORS.get(cat, "#607D8B"),
            fontweight="bold")

plt.tight_layout()
out6 = OUT_DIR / "06_multi_hook_grouped.png"
plt.savefig(out6, dpi=150, bbox_inches="tight")
plt.close()
print(f"  -> {out6.name}")

# =============================================================================
# Figure 7 — Summary dashboard (2×3 mini-panels)
# =============================================================================
print("Plotting Figure 7: Summary dashboard ...")

fig, axs = plt.subplots(2, 3, figsize=(20, 11))
fig.suptitle("Stress Anomaly Dataset — Summary Dashboard", fontsize=15, fontweight="bold")

def bar_panel(ax, vals, title, ylabel, unit_div=1, unit="", highlight_threshold=None):
    vv = [v / unit_div for v in vals]
    bars = ax.bar(x, vv, color=colors, edgecolor="white", linewidth=0.3, zorder=3)
    if vv[0]:
        ax.axhline(vv[0], color="black", ls="--", lw=1.0, alpha=0.7)
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.set_ylabel(f"{ylabel}{' (' + unit + ')' if unit else ''}", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(xlabels, rotation=60, ha="right", fontsize=7)
    if highlight_threshold and vv[0]:
        for i, v in enumerate(vv):
            if v > vv[0] * highlight_threshold:
                bars[i].set_edgecolor("red")
                bars[i].set_linewidth(1.5)

bar_panel(axs[0, 0], [s["metrics"].get("hook.fapi_ul_tti_request.max", 0) for s in scenarios],
          "FAPI-UL Hook Max", "Latency", unit_div=1000, unit="µs", highlight_threshold=3)

bar_panel(axs[0, 1], [s["metrics"].get("hook.fapi_ul_tti_request.p99", 0) for s in scenarios],
          "FAPI-UL Hook p99", "Latency", unit_div=1000, unit="µs", highlight_threshold=3)

bar_panel(axs[0, 2], [s["metrics"].get("bsr.bytes.max", 0) for s in scenarios],
          "BSR Peak Buffer", "Bytes", unit_div=1024, unit="KB", highlight_threshold=5)

bar_panel(axs[1, 0], [s["metrics"].get("harq.failures.total", 0) for s in scenarios],
          "HARQ Failures", "Count")

bar_panel(axs[1, 1], [s["metrics"].get("sinr.avg", 0) for s in scenarios],
          "Average SINR", "dB")

bar_panel(axs[1, 2], [s["metrics"].get("hook.rlc_ul_sdu_delivered.max", 0) for s in scenarios],
          "RLC-UL SDU Hook Max", "Latency", unit_div=1000, unit="µs", highlight_threshold=3)

# Shared legend
fig.legend(handles=legend_patches, loc="lower center", ncol=len(legend_patches),
           fontsize=9, title="Category", title_fontsize=10, bbox_to_anchor=(0.5, -0.01))

plt.tight_layout(rect=[0, 0.04, 1, 1])
out7 = OUT_DIR / "07_summary_dashboard.png"
plt.savefig(out7, dpi=150, bbox_inches="tight")
plt.close()
print(f"  -> {out7.name}")

# =============================================================================
# Done
# =============================================================================
print(f"\nAll plots saved to: {OUT_DIR}")
print(f"  01_hook_latency_comparison.png")
print(f"  02_bsr_comparison.png")
print(f"  03_harq_sinr_comparison.png")
print(f"  04_anomaly_heatmap.png")
print(f"  05_timeseries_overlay.png")
print(f"  06_multi_hook_grouped.png")
print(f"  07_summary_dashboard.png")
