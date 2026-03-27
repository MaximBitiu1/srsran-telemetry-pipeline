#!/usr/bin/env python3
"""
BEP Extension — Supervisor Presentation Plots
==============================================
Generates 5 publication-quality figures summarising the stress anomaly
dataset collected on top of the srsRAN 5G NR jBPF telemetry pipeline.

Usage:
    python3 plot_bep_presentation.py [dataset_dir]

Default dataset: ~/Desktop/dataset/stress_20260325_204950
Output:          ~/Desktop/project_extension/figures/
"""
import json, re, sys, csv as csv_mod
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
from pathlib import Path
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────
if len(sys.argv) > 1:
    DATASET = Path(sys.argv[1])
else:
    base = Path.home() / "Desktop" / "dataset"
    candidates = sorted(base.glob("stress_*"), reverse=True)
    DATASET = candidates[0] if candidates else None

if not DATASET or not DATASET.exists():
    print("ERROR: dataset directory not found"); sys.exit(1)

OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)
print(f"Dataset : {DATASET}")
print(f"Figures → {OUT}")

# ── Style ─────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor":   "#F7F9FC",
    "axes.grid":        True,
    "grid.alpha":       0.35,
    "grid.linestyle":   "--",
    "font.family":      "DejaVu Sans",
    "font.size":        11,
    "axes.titlesize":   13,
    "axes.titleweight": "bold",
    "axes.labelsize":   11,
    "legend.fontsize":  9,
    "figure.dpi":       150,
})

CAT_COLOR = {
    "baseline": "#1976D2",
    "cpu":      "#FF7043",
    "memory":   "#AB47BC",
    "sched":    "#EF5350",
    "traffic":  "#43A047",
    "combined": "#FF8F00",
}
CAT_LABEL = {
    "baseline": "Baseline",
    "cpu":      "CPU stressor",
    "memory":   "Memory pressure",
    "sched":    "Scheduler attack",
    "traffic":  "Traffic flood",
    "combined": "Combined",
}

# ── Parser ────────────────────────────────────────────────────────────────────
def parse_log(path):
    records = defaultdict(list)
    with open(path, errors='replace') as f:
        for line in f:
            m = re.match(r'^time="([^"]+)".*msg="REC: (.+)"$', line.strip())
            if not m: continue
            raw = m.group(2).replace('\\"', '"')
            if raw.startswith('"'): raw = raw[1:]
            if raw.endswith('"'):   raw = raw[:-1]
            try: d = json.loads(raw)
            except: continue
            schema = d.get("_schema_proto_msg", "")
            pkg    = d.get("_schema_proto_package", "")
            if schema == "crc_stats" and pkg == "fapi_gnb_crc_stats":
                schema = "fapi_crc_stats"
            records[schema].append(d)
    return records

def extract(records):
    m = {}
    hook_agg = defaultdict(lambda: {"max": [], "p99": [], "p50": []})
    for r in records.get("jbpf_out_perf_list", []):
        for h in r.get("hookPerf", []):
            n = h.get("hookName", "")
            hook_agg[n]["max"].append(int(h.get("max", 0)))
            hook_agg[n]["p99"].append(int(h.get("p99", 0)))
            hook_agg[n]["p50"].append(int(h.get("p50", 0)))
    for n, a in hook_agg.items():
        if a["max"]:
            m[f"hook.{n}.max_us"]    = max(a["max"]) / 1000
            m[f"hook.{n}.p99_us"]    = max(a["p99"]) / 1000
            m[f"hook.{n}.p50_med_us"] = float(np.median(a["p50"])) / 1000

    bsr = []
    for r in records.get("bsr_stats", []):
        for s in r.get("stats", []):
            bsr.append(int(s.get("bytes", 0)))
    if bsr:
        m["bsr.max_mb"]    = max(bsr) / 1e6
        m["bsr.p95_mb"]    = float(np.percentile(bsr, 95)) / 1e6
        m["bsr.median_mb"] = float(np.median(bsr)) / 1e6

    sinr, harq_f, mcs_ul = [], [], []
    for r in records.get("crc_stats", []):
        for s in r.get("stats", []):
            if s.get("duUeIndex", 0) == 513: continue
            harq_f.append(s.get("harqFailure", 0))
            if s.get("cntSinr", 0) > 0:
                sinr.append(s["sumSinr"] / s["cntSinr"])
    for r in records.get("ul_config_stats", []):
        for s in r.get("stats", []):
            cnt = s.get("l1Cnt", 0)
            if cnt > 0:
                v = s.get("l1McsAvg", 0) / cnt
                if v > 0: mcs_ul.append(v)

    if sinr:
        m["sinr.mean"] = float(np.mean(sinr))
        m["sinr.min"]  = float(np.min(sinr))
    if harq_f:
        m["harq.failures"] = sum(harq_f)
    if mcs_ul:
        m["mcs_ul.mean"] = float(np.mean(mcs_ul))
    return m

# ── Load scenarios ────────────────────────────────────────────────────────────
scenarios = []
with open(DATASET / "manifest.csv", newline="") as f:
    for row in csv_mod.DictReader(f):
        sid  = row["id"].strip()
        lbl  = row["label"].strip()
        cat  = row["category"].strip()
        stat = row["status"].strip()
        lf   = row["logfile"].strip()
        if stat == "complete" and lf and Path(lf).exists():
            recs = parse_log(lf)
            met  = extract(recs)
            scenarios.append({"id": sid, "label": lbl, "category": cat, "metrics": met})

scenarios.sort(key=lambda x: x["id"])

# Find FAPI-UL hook key
FAPI_UL = None
for sc in scenarios:
    for k in sc["metrics"]:
        if k.startswith("hook.") and "fapi" in k.lower() and "ul" in k.lower() and k.endswith(".max_us"):
            FAPI_UL = k
            break
    if FAPI_UL: break

labels     = [sc["label"] for sc in scenarios]
short_lbls = [re.sub(r"^\d+_", "", l) for l in labels]
categories = [sc["category"] for sc in scenarios]
colors     = [CAT_COLOR.get(c, "#607D8B") for c in categories]
N = len(scenarios)
x = np.arange(N)

fapi_max = np.array([sc["metrics"].get(FAPI_UL, 0)           for sc in scenarios])
bsr_max  = np.array([sc["metrics"].get("bsr.max_mb", 0)       for sc in scenarios])
sinr     = np.array([sc["metrics"].get("sinr.mean", 0)        for sc in scenarios])
mcs      = np.array([sc["metrics"].get("mcs_ul.mean", 0)      for sc in scenarios])
harq_f   = np.array([sc["metrics"].get("harq.failures", 0)    for sc in scenarios])

base_fapi = fapi_max[0]
base_bsr  = bsr_max[0]

legend_handles = [mpatches.Patch(color=CAT_COLOR[c], label=CAT_LABEL[c])
                  for c in CAT_COLOR if any(cat == c for cat in categories)]

def save(fig, name):
    path = OUT / name
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"  -> {name}")

# ══════════════════════════════════════════════════════════════════════════════
# Figure 1 — FAPI-UL hook latency (log scale) + BSR side-by-side
# ══════════════════════════════════════════════════════════════════════════════
print("Plotting Figure 1: Hook latency + BSR overview ...")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

# Left: hook latency
bars1 = ax1.bar(x, fapi_max, color=colors, edgecolor="white", linewidth=0.5, zorder=3)
ax1.axhline(base_fapi, color="#1976D2", linestyle="--", linewidth=1.4,
            label=f"Baseline ({base_fapi:.0f} µs)", zorder=4)
ax1.set_yscale("log")
ax1.set_ylabel("FAPI-UL hook max latency (µs)")
ax1.set_title("jBPF FAPI-UL Hook Latency Under Stress")
ax1.set_xticks(x)
ax1.set_xticklabels(short_lbls, rotation=55, ha="right", fontsize=7.5)
ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}"))
# annotate top-4 spikes
top4 = np.argsort(fapi_max)[-4:]
for i in top4:
    ax1.annotate(f"{fapi_max[i]/1000:.1f} ms",
                 xy=(i, fapi_max[i]), xytext=(0, 6),
                 textcoords="offset points", ha="center", fontsize=7.5,
                 fontweight="bold", color="black")
ax1.legend(handles=legend_handles + [mpatches.Patch(color="none", label=f"Baseline = {base_fapi:.0f} µs")],
           loc="upper left", fontsize=8)

# Right: BSR
bars2 = ax2.bar(x, bsr_max * 1000, color=colors, edgecolor="white", linewidth=0.5, zorder=3)
ax2.axhline(base_bsr * 1000, color="#1976D2", linestyle="--", linewidth=1.4,
            label=f"Baseline ({base_bsr*1000:.0f} KB)", zorder=4)
ax2.set_ylabel("UL Buffer (BSR) max (KB)")
ax2.set_title("UL Buffer Status Report (BSR) Under Stress")
ax2.set_xticks(x)
ax2.set_xticklabels(short_lbls, rotation=55, ha="right", fontsize=7.5)
ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
top4b = np.argsort(bsr_max)[-4:]
for i in top4b:
    ax2.annotate(f"{bsr_max[i]*1000/1024:.0f} KB",
                 xy=(i, bsr_max[i]*1000), xytext=(0, 5),
                 textcoords="offset points", ha="center", fontsize=7.5,
                 fontweight="bold", color="black")
ax2.legend(handles=legend_handles, loc="upper left", fontsize=8)

fig.suptitle("srsRAN 5G NR — Stress Anomaly Dataset: Per-Scenario Telemetry\n"
             "(fading baseline: K=3 dB, SNR=25 dB, f_d=5 Hz)", fontsize=13, fontweight="bold")
plt.tight_layout()
save(fig, "fig1_hook_bsr_overview.png")

# ══════════════════════════════════════════════════════════════════════════════
# Figure 2 — Signal-space scatter: hook latency vs BSR (log-log)
# ══════════════════════════════════════════════════════════════════════════════
print("Plotting Figure 2: Signal space scatter ...")
fig, ax = plt.subplots(figsize=(10, 7))

for sc, c, sl in zip(scenarios, colors, short_lbls):
    fv = sc["metrics"].get(FAPI_UL, 0.1)
    bv = sc["metrics"].get("bsr.max_mb", 0.001) * 1000  # KB
    ax.scatter(fv, bv, color=c, s=90, zorder=5, edgecolors="white", linewidth=0.8)
    # label only notable points
    if fv > 200 or bv > 8000:
        ax.annotate(sl, (fv, bv), fontsize=7, xytext=(5, 3),
                    textcoords="offset points", color="black")

# GRC broker "reachable region" shading
ax.axhspan(0, 4000, xmin=0, xmax=0.06, alpha=0.08, color="#1976D2",
           label="GRC broker region (typical)")
ax.axvspan(0, 200, alpha=0.08, color="#1976D2")
ax.text(30, 4500, "GRC broker\n(channel only)\nreachable region",
        color="#1976D2", fontsize=8, alpha=0.8)

ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("FAPI-UL hook max latency (µs, log scale)")
ax.set_ylabel("Max UL buffer — BSR (KB, log scale)")
ax.set_title("Anomaly Signal Space: Hook Latency vs Buffer Size\n"
             "Each point = one 90-second scenario run")
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}"))
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
ax.legend(handles=legend_handles, loc="lower right", fontsize=9)

# Quadrant labels
ax.text(3000, 40000, "HOOK SPIKE\n+ BSR SPIKE\n(combined stressors)",
        ha="center", va="center", fontsize=8.5, color="#FF8F00",
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFF8E1", alpha=0.8))
ax.text(3000, 2500, "HOOK SPIKE ONLY\n(sched attack)",
        ha="center", va="center", fontsize=8.5, color="#EF5350",
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFEBEE", alpha=0.8))
ax.text(40, 27000, "BSR SPIKE ONLY\n(traffic flood)",
        ha="center", va="center", fontsize=8.5, color="#43A047",
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#E8F5E9", alpha=0.8))

plt.tight_layout()
save(fig, "fig2_signal_space.png")

# ══════════════════════════════════════════════════════════════════════════════
# Figure 3 — Normalised anomaly score heatmap (scenarios × metrics)
# ══════════════════════════════════════════════════════════════════════════════
print("Plotting Figure 3: Anomaly heatmap ...")

METRICS = {
    "FAPI-UL\nhook (µs)": fapi_max,
    "BSR max\n(KB)":       bsr_max * 1000,
    "SINR\n(dB, inverted)": -sinr + max(sinr),  # invert so higher = worse
    "MCS UL\n(inverted)":   -mcs + max(mcs),
}

mat = np.zeros((N, len(METRICS)))
for j, (_, vals) in enumerate(METRICS.items()):
    vmin, vmax = vals.min(), vals.max()
    if vmax > vmin:
        mat[:, j] = (vals - vmin) / (vmax - vmin)

fig, ax = plt.subplots(figsize=(9, 11))
im = ax.imshow(mat, aspect="auto", cmap="YlOrRd", vmin=0, vmax=1,
               interpolation="nearest")

ax.set_xticks(range(len(METRICS)))
ax.set_xticklabels(list(METRICS.keys()), fontsize=9)
ax.set_yticks(range(N))
ax.set_yticklabels(short_lbls, fontsize=8)

# Category colour stripe on left
for i, cat in enumerate(categories):
    ax.add_patch(plt.Rectangle((-0.8, i - 0.5), 0.5, 1.0,
                                color=CAT_COLOR.get(cat, "grey"), clip_on=False))

ax.set_xlim(-1, len(METRICS) - 0.5)
ax.set_title("Normalised Anomaly Score per Scenario and Metric\n"
             "(0 = baseline, 1 = maximum anomaly observed)", fontsize=12)

cbar = fig.colorbar(im, ax=ax, shrink=0.5, pad=0.02)
cbar.set_label("Normalised anomaly score", fontsize=9)

# Annotate cells > 0.7
for i in range(N):
    for j in range(len(METRICS)):
        v = mat[i, j]
        if v > 0.7:
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    fontsize=7.5, fontweight="bold",
                    color="white" if v > 0.85 else "black")

ax.legend(handles=legend_handles, loc="lower right",
          bbox_to_anchor=(1.0, -0.14), fontsize=8, ncol=3)
plt.tight_layout()
save(fig, "fig3_anomaly_heatmap.png")

# ══════════════════════════════════════════════════════════════════════════════
# Figure 4 — SINR vs MCS: stressors vs GRC broker signals
# ══════════════════════════════════════════════════════════════════════════════
print("Plotting Figure 4: SINR/MCS invariance under stress ...")
fig, axes = plt.subplots(1, 2, figsize=(13, 5))

# Left: SINR per scenario
ax = axes[0]
ax.bar(x, sinr, color=colors, edgecolor="white", linewidth=0.5, zorder=3)
ax.axhline(sinr[0], color="#1976D2", linestyle="--", linewidth=1.4,
           label=f"Baseline SINR ({sinr[0]:.1f} dB)")
ax.set_ylim(20, 27)
ax.set_ylabel("Mean SINR (dB)")
ax.set_title("SINR: Stressors cause only ~2 dB drop\n(GRC broker can cause 10+ dB)")
ax.set_xticks(x)
ax.set_xticklabels(short_lbls, rotation=55, ha="right", fontsize=7.5)
ax.legend(fontsize=9)

# Right: MCS per scenario
ax = axes[1]
ax.bar(x, mcs, color=colors, edgecolor="white", linewidth=0.5, zorder=3)
ax.axhline(mcs[0], color="#1976D2", linestyle="--", linewidth=1.4,
           label=f"Baseline MCS ({mcs[0]:.1f})")
ax.set_ylim(24, 30)
ax.set_ylabel("Mean UL MCS")
ax.set_title("UL MCS: Stays at maximum — no link adaptation response\n"
             "(GRC broker drives MCS down to 14 at SNR=15 dB)")
ax.set_xticks(x)
ax.set_xticklabels(short_lbls, rotation=55, ha="right", fontsize=7.5)
ax.legend(fontsize=9)

# shared legend
fig.legend(handles=legend_handles, loc="lower center",
           ncol=len(legend_handles), fontsize=9,
           bbox_to_anchor=(0.5, -0.04))
fig.suptitle("SINR and MCS Invariance Under System-Level Stressors\n"
             "Key difference from GRC channel broker anomalies", fontsize=13, fontweight="bold")
plt.tight_layout()
save(fig, "fig4_sinr_mcs_invariance.png")

# ══════════════════════════════════════════════════════════════════════════════
# Figure 5 — Summary: multiplier vs baseline, grouped by category
# ══════════════════════════════════════════════════════════════════════════════
print("Plotting Figure 5: Anomaly multiplier summary ...")

# Per-category: max of (fapi_max / base_fapi) and (bsr_max / base_bsr)
cats_ordered = ["cpu", "memory", "sched", "traffic", "combined"]
cat_fapi_mult = {}
cat_bsr_mult  = {}
for cat in cats_ordered:
    idxs = [i for i, c in enumerate(categories) if c == cat]
    cat_fapi_mult[cat] = max(fapi_max[i] / base_fapi for i in idxs)
    cat_bsr_mult[cat]  = max(bsr_max[i]  / base_bsr  for i in idxs)

fig, ax = plt.subplots(figsize=(10, 6))
xc = np.arange(len(cats_ordered))
w  = 0.35

bars_f = ax.bar(xc - w/2, [cat_fapi_mult[c] for c in cats_ordered],
                width=w, label="FAPI-UL hook latency (max/baseline)",
                color=[CAT_COLOR[c] for c in cats_ordered],
                edgecolor="white", linewidth=0.5, alpha=0.95)
bars_b = ax.bar(xc + w/2, [cat_bsr_mult[c] for c in cats_ordered],
                width=w, label="BSR buffer size (max/baseline)",
                color=[CAT_COLOR[c] for c in cats_ordered],
                edgecolor="black", linewidth=0.8, alpha=0.5,
                hatch="///")

ax.axhline(1.0, color="black", linestyle="--", linewidth=1.2, label="Baseline (1×)")
ax.set_yscale("log")
ax.set_ylabel("Anomaly multiplier vs baseline (log scale)")
ax.set_title("Maximum Anomaly Magnitude by Stressor Category\n"
             "Solid = hook latency spike   Hatched = BSR spike")
ax.set_xticks(xc)
ax.set_xticklabels([CAT_LABEL[c] for c in cats_ordered], fontsize=11)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}×"))

for bar in bars_f:
    h = bar.get_height()
    if h > 2:
        ax.text(bar.get_x() + bar.get_width()/2, h * 1.15,
                f"{h:.0f}×", ha="center", va="bottom", fontsize=9, fontweight="bold")
for bar in bars_b:
    h = bar.get_height()
    if h > 2:
        ax.text(bar.get_x() + bar.get_width()/2, h * 1.15,
                f"{h:.0f}×", ha="center", va="bottom", fontsize=9)

ax.legend(fontsize=9)
ax.set_ylim(0.5, 300)
plt.tight_layout()
save(fig, "fig5_category_summary.png")

print(f"\nAll figures saved to {OUT}")
