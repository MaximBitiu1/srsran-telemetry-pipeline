"""
Generate architecture and pipeline diagrams for the srsRAN jBPF thesis project.
Outputs PNG files to docs/figures/.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe
import numpy as np
import os

OUT = os.path.join(os.path.dirname(__file__), "../docs/figures")
os.makedirs(OUT, exist_ok=True)

# ── Colour palette ─────────────────────────────────────────────────────────────
C = {
    "gnb":     "#1a6faf",   # deep blue
    "ue":      "#2e8b57",   # sea green
    "broker":  "#8b6914",   # dark gold
    "jrtc":    "#6a0dad",   # purple
    "infra":   "#b22222",   # dark red
    "data":    "#1a8c8c",   # teal
    "grafana": "#e65c00",   # orange
    "bg":      "#f8f9fa",
    "arrow":   "#444444",
    "text":    "#1a1a1a",
    "light":   "#ddeeff",
}


def box(ax, x, y, w, h, label, sublabel="", color="#1a6faf", fontsize=9,
        radius=0.04, alpha=0.92):
    """Draw a rounded-rectangle box with optional sub-label."""
    fancy = FancyBboxPatch((x - w/2, y - h/2), w, h,
                           boxstyle=f"round,pad={radius}",
                           facecolor=color, edgecolor="white",
                           linewidth=1.5, alpha=alpha, zorder=3)
    ax.add_patch(fancy)
    if sublabel:
        ax.text(x, y + h * 0.12, label, ha="center", va="center",
                fontsize=fontsize, fontweight="bold", color="white", zorder=4)
        ax.text(x, y - h * 0.22, sublabel, ha="center", va="center",
                fontsize=fontsize - 1.5, color="white", alpha=0.88, zorder=4)
    else:
        ax.text(x, y, label, ha="center", va="center",
                fontsize=fontsize, fontweight="bold", color="white", zorder=4)


def arrow(ax, x1, y1, x2, y2, label="", color="#444444", lw=1.5,
          style="->", label_offset=(0, 0)):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color,
                                lw=lw, connectionstyle="arc3,rad=0.0"),
                zorder=2)
    if label:
        mx, my = (x1 + x2) / 2 + label_offset[0], (y1 + y2) / 2 + label_offset[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=7.5,
                color=color, zorder=5,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))


# ══════════════════════════════════════════════════════════════════════════════
# Figure 1 — Full System Architecture
# ══════════════════════════════════════════════════════════════════════════════
def fig_system_architecture():
    fig, ax = plt.subplots(figsize=(14, 9))
    fig.patch.set_facecolor(C["bg"])
    ax.set_facecolor(C["bg"])
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 9)
    ax.axis("off")
    ax.set_title("srsRAN 5G NR jBPF Telemetry Pipeline — System Architecture",
                 fontsize=13, fontweight="bold", color=C["text"], pad=12)

    # ── LEFT COLUMN: Radio stack ───────────────────────────────────────────
    # jrtc
    box(ax, 3.5, 8.1, 2.6, 0.7, "jrt-controller (jrtc)",
        "eBPF runtime  |  port 3001", color=C["jrtc"], fontsize=8.5)

    # gNB
    box(ax, 3.5, 6.7, 2.6, 1.0, "srsRAN gNB",
        "TX :4000  RX :4001\njBPF-instrumented fork", color=C["gnb"], fontsize=8.5)

    # ZMQ Broker
    box(ax, 3.5, 5.1, 2.6, 0.9, "ZMQ Channel Broker",
        "Fading · AWGN · Interference\nGRC Python", color=C["broker"], fontsize=8.5)

    # srsUE
    box(ax, 3.5, 3.5, 2.6, 0.9, "srsUE (NR-only)",
        "TX :2001  RX :2000\nnetns ue1  |  tun_srsue", color=C["ue"], fontsize=8.5)

    # iperf3 / traffic
    box(ax, 3.5, 2.1, 2.6, 0.7, "Traffic / Test",
        "iperf3 UL :5201  DL :5202  |  ping", color=C["ue"], fontsize=8, alpha=0.8)

    # Radio arrows (left column)
    arrow(ax, 3.5, 7.75, 3.5, 7.17, "IPC shm")
    arrow(ax, 3.5, 6.2, 3.5, 5.55, "ZMQ :4000/:4001")
    arrow(ax, 3.5, 4.65, 3.5, 4.0, "ZMQ :2000/:2001")
    arrow(ax, 3.5, 3.05, 3.5, 2.45, "UDP/ICMP")

    # ── CENTRE: eBPF codelets ─────────────────────────────────────────────
    box(ax, 7.0, 6.7, 2.2, 1.0, "~60 eBPF Codelets",
        "11 codelet sets\n17 telemetry schemas", color=C["jrtc"], fontsize=8.5)

    # Codelet arrows
    arrow(ax, 4.8, 6.7, 5.9, 6.7, "hook", color=C["jrtc"])
    arrow(ax, 8.1, 6.7, 9.0, 6.7, "protobuf\nUDP :20788", color=C["jrtc"],
          label_offset=(0, 0.18))

    # Reverse Proxy
    box(ax, 7.0, 5.1, 2.2, 0.7, "Reverse Proxy",
        "IPC→TCP  |  :30450", color=C["data"], fontsize=8.5)
    arrow(ax, 4.8, 6.4, 5.9, 5.1, color=C["data"])
    arrow(ax, 8.1, 5.1, 9.0, 5.1, "gRPC\n:20789", color=C["data"],
          label_offset=(0, 0.18))

    # ── RIGHT COLUMN: Data pipeline ───────────────────────────────────────
    # Decoder
    box(ax, 10.5, 6.7, 2.2, 0.9, "Decoder",
        "gRPC :20789  UDP :20788\n/tmp/decoder.log", color=C["data"], fontsize=8.5)

    # InfluxDB
    box(ax, 10.5, 5.1, 2.2, 0.7, "InfluxDB 1.x",
        "db: srsran_telemetry  |  :8086", color=C["infra"], fontsize=8.5)
    arrow(ax, 10.5, 6.25, 10.5, 5.45, "line protocol")

    # Grafana
    box(ax, 10.5, 3.5, 2.2, 0.9, "Grafana Dashboard",
        "45 panels  |  :3000\nhttp://localhost:3000/…", color=C["grafana"], fontsize=8.5)
    arrow(ax, 10.5, 4.75, 10.5, 3.95, "InfluxQL")

    # telemetry_to_influxdb.py label
    ax.text(10.5, 5.83, "telemetry_to_influxdb.py", ha="center", va="center",
            fontsize=7, color=C["data"], style="italic")

    # Decoder → ingestor → InfluxDB connector
    arrow(ax, 9.0, 6.7, 9.4, 6.7, color=C["data"])

    # ── BOTTOM: Standard metrics channel ─────────────────────────────────
    box(ax, 7.0, 2.1, 2.8, 0.8, "Standard Metrics (WebSocket)",
        "remote_control  |  ws://127.0.0.1:8001", color="#555555", fontsize=8)
    arrow(ax, 4.8, 6.1, 5.6, 2.5, color="#888888", style="-|>")
    ax.text(5.0, 4.2, "JSON metrics\n~1s aggregate", ha="center", va="center",
            fontsize=7, color="#666666", style="italic")
    arrow(ax, 8.4, 2.1, 9.5, 2.1, color="#888888",
          label="capture_standard_metrics.py\n→ /tmp/standard_metrics.jsonl",
          label_offset=(0.6, 0.3))

    # ── LEGEND ────────────────────────────────────────────────────────────
    legend_items = [
        mpatches.Patch(color=C["jrtc"], label="jBPF / Codelets"),
        mpatches.Patch(color=C["gnb"],  label="gNB (Radio)"),
        mpatches.Patch(color=C["ue"],   label="UE / Traffic"),
        mpatches.Patch(color=C["broker"], label="Channel Broker"),
        mpatches.Patch(color=C["data"], label="Data Pipeline"),
        mpatches.Patch(color=C["infra"], label="Storage / DB"),
        mpatches.Patch(color=C["grafana"], label="Visualisation"),
    ]
    ax.legend(handles=legend_items, loc="lower left", fontsize=8,
              framealpha=0.9, ncol=4, bbox_to_anchor=(0.0, 0.0))

    plt.tight_layout()
    path = os.path.join(OUT, "fig_system_architecture.png")
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=C["bg"])
    plt.close()
    print(f"Saved {path}")


# ══════════════════════════════════════════════════════════════════════════════
# Figure 2 — Telemetry Data Flow
# ══════════════════════════════════════════════════════════════════════════════
def fig_telemetry_flow():
    fig, ax = plt.subplots(figsize=(13, 6))
    fig.patch.set_facecolor(C["bg"])
    ax.set_facecolor(C["bg"])
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title("jBPF Telemetry Data Flow — From Hook to Dashboard",
                 fontsize=12, fontweight="bold", color=C["text"], pad=10)

    stages = [
        (1.2, 3.0, 1.6, 0.9, "gNB Function\nCall Sites", "22 hook points\nacross MAC/RLC/PDCP/FAPI", C["gnb"]),
        (3.4, 3.0, 1.6, 0.9, "eBPF Codelets", "~60 codelets\n17 schemas (Protobuf)", C["jrtc"]),
        (5.6, 3.0, 1.6, 0.9, "Decoder", "gRPC :20789\nUDP :20788", C["data"]),
        (7.8, 3.0, 1.8, 0.9, "telemetry_to_\ninfluxdb.py", "Parse → delta\n→ line protocol", C["data"]),
        (10.1, 3.0, 1.6, 0.9, "InfluxDB 1.x", "srsran_telemetry\n:8086", C["infra"]),
        (12.1, 3.0, 1.4, 0.9, "Grafana\n45 panels", ":3000", C["grafana"]),
    ]

    for x, y, w, h, label, sublabel, color in stages:
        box(ax, x, y, w, h, label, sublabel, color=color, fontsize=8.5)

    xs = [s[0] for s in stages]
    for i in range(len(xs) - 1):
        x1 = xs[i] + stages[i][2] / 2
        x2 = xs[i+1] - stages[i+1][2] / 2
        arrow(ax, x1, 3.0, x2, 3.0, color=C["arrow"], lw=2.0)

    # Timing annotations below
    timings = [
        (1.2, 1.9, "Every 1 ms slot"),
        (3.4, 1.9, "Per invocation"),
        (5.6, 1.9, "Buffered UDP"),
        (7.8, 1.9, "Cumulative →\ndelta conversion"),
        (10.1, 1.9, "Line protocol\nbatch write"),
        (12.1, 1.9, "InfluxQL\nauto-refresh"),
    ]
    for x, y, txt in timings:
        ax.text(x, y, txt, ha="center", va="top", fontsize=7.5,
                color="#555555", style="italic")
        ax.plot([x, x], [2.55, 2.0], color="#aaaaaa", lw=0.8, ls="--", zorder=1)

    # Latency bar
    ax.annotate("", xy=(12.8, 0.9), xytext=(0.4, 0.9),
                arrowprops=dict(arrowstyle="<->", color="#888888", lw=1.5))
    ax.text(6.6, 0.65, "End-to-end latency: ~2–5 s (InfluxDB write interval + Grafana poll)",
            ha="center", va="center", fontsize=8, color="#555555")

    plt.tight_layout()
    path = os.path.join(OUT, "fig_telemetry_flow.png")
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=C["bg"])
    plt.close()
    print(f"Saved {path}")


# ══════════════════════════════════════════════════════════════════════════════
# Figure 3 — Channel Broker Architecture
# ══════════════════════════════════════════════════════════════════════════════
def fig_channel_broker():
    fig, ax = plt.subplots(figsize=(12, 6.5))
    fig.patch.set_facecolor(C["bg"])
    ax.set_facecolor(C["bg"])
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6.5)
    ax.axis("off")
    ax.set_title("ZMQ Channel Broker — IQ Sample Impairment Pipeline",
                 fontsize=12, fontweight="bold", color=C["text"], pad=10)

    # gNB
    box(ax, 1.2, 3.25, 1.6, 2.4, "srsRAN gNB",
        "TX → :4000\nRX ← :4001", color=C["gnb"], fontsize=8.5)

    # Broker (large centre box)
    broker_bg = FancyBboxPatch((3.2, 1.0), 5.6, 4.5,
                               boxstyle="round,pad=0.1",
                               facecolor="#fff8e1", edgecolor=C["broker"],
                               linewidth=2, alpha=0.95, zorder=2)
    ax.add_patch(broker_bg)
    ax.text(6.0, 5.25, "GRC Python Channel Broker", ha="center", va="center",
            fontsize=10, fontweight="bold", color=C["broker"], zorder=3)

    sub_boxes = [
        (4.3, 4.1, 1.5, 0.7, "AWGN\nNoise Floor", "#b8860b"),
        (6.0, 4.1, 1.5, 0.7, "Fading Model\nRician / Rayleigh", "#b8860b"),
        (7.7, 4.1, 1.5, 0.7, "Interference\nCW / Narrowband", "#b8860b"),
        (4.3, 2.8, 1.5, 0.7, "EPA / EVA / ETU\nMultipath", "#9c6900"),
        (6.0, 2.8, 1.5, 0.7, "CFO / Burst\nDrops", "#9c6900"),
        (7.7, 2.8, 1.5, 0.7, "Time-varying\nScenarios", "#9c6900"),
        (6.0, 1.7, 2.4, 0.7, "Live QT GUI Control\n(Doppler · K-factor · SNR)", "#7a5000"),
    ]
    for x, y, w, h, lbl, col in sub_boxes:
        box(ax, x, y, w, h, lbl, color=col, fontsize=7.5, radius=0.03)

    # srsUE
    box(ax, 10.8, 3.25, 1.6, 2.4, "srsUE (NR)",
        "RX ← :2000\nTX → :2001", color=C["ue"], fontsize=8.5)

    # Arrows
    arrow(ax, 2.0, 3.6, 3.25, 3.6, "DL IQ", color=C["gnb"], lw=2)
    arrow(ax, 3.25, 2.9, 2.0, 2.9, "UL IQ", color=C["ue"], lw=2)
    arrow(ax, 8.75, 3.6, 10.0, 3.6, "DL IQ", color=C["gnb"], lw=2)
    arrow(ax, 10.0, 2.9, 8.75, 2.9, "UL IQ", color=C["ue"], lw=2)

    # Scenario label
    ax.text(6.0, 0.4, "10 collected scenarios: Baseline · Time-varying · Steady impairment · RLF cycles",
            ha="center", va="center", fontsize=8, color="#555555", style="italic")

    plt.tight_layout()
    path = os.path.join(OUT, "fig_channel_broker.png")
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=C["bg"])
    plt.close()
    print(f"Saved {path}")


# ══════════════════════════════════════════════════════════════════════════════
# Figure 4 — jBPF vs Standard Telemetry Comparison
# ══════════════════════════════════════════════════════════════════════════════
def fig_jbpf_vs_standard():
    fig, ax = plt.subplots(figsize=(13, 7))
    fig.patch.set_facecolor(C["bg"])
    ax.set_facecolor(C["bg"])
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title("jBPF vs Standard srsRAN Telemetry — Capability Comparison",
                 fontsize=12, fontweight="bold", color=C["text"], pad=10)

    # Column headers
    ax.text(3.0, 6.6, "Standard srsRAN Metrics\n(WebSocket / Grafana GUI)",
            ha="center", va="center", fontsize=10, fontweight="bold",
            color="white",
            bbox=dict(boxstyle="round,pad=0.4", fc="#555555", ec="none"))
    ax.text(10.0, 6.6, "jBPF Hook Telemetry\n(Our Pipeline)",
            ha="center", va="center", fontsize=10, fontweight="bold",
            color="white",
            bbox=dict(boxstyle="round,pad=0.4", fc=C["jrtc"], ec="none"))

    categories = [
        ("Temporal Resolution",    "~1 s aggregate",               "1 ms per slot"),
        ("MCS",                    "DL/UL average",                "Per-slot, min/max envelope"),
        ("SINR",                   "Average",                      "Per-CRC event"),
        ("BSR",                    "~1 s average",                 "Per-slot report"),
        ("HARQ failures",          "Count per window",             "Count + consecutive retx state"),
        ("RLC SDU latency",        "Average/max",                  "Per-slot avg/max + distribution"),
        ("Hook execution latency", "NOT AVAILABLE",                "p50/p90/p95/p99 per hook"),
        ("Grafana panels",         "~20 panels",                   "45 panels"),
        ("Infrastructure faults",  "Invisible",                    "Visible via hook_p99 spikes"),
        ("CPU overhead",           "Negligible (poll-based)",       "~3.3% of 1 core @ 25 Mbps"),
    ]

    row_h = 0.48
    y0 = 6.0
    for i, (cat, std, jbpf) in enumerate(categories):
        y = y0 - i * row_h
        bg_col = "#f0f0f0" if i % 2 == 0 else "white"
        ax.add_patch(mpatches.FancyBboxPatch((0.2, y - row_h * 0.48), 12.6, row_h * 0.92,
                     boxstyle="square,pad=0", facecolor=bg_col,
                     edgecolor="none", zorder=1))

        ax.text(1.0, y - row_h * 0.04, cat, ha="left", va="center",
                fontsize=8.5, fontweight="bold", color=C["text"], zorder=2)

        # Standard column
        color_std = "#cc2222" if "NOT" in std or "Invisible" in std else "#444444"
        ax.text(3.0, y - row_h * 0.04, std, ha="center", va="center",
                fontsize=8.5, color=color_std, zorder=2)

        # jBPF column
        ax.text(10.0, y - row_h * 0.04, jbpf, ha="center", va="center",
                fontsize=8.5, color=C["jrtc"], fontweight="bold", zorder=2)

        # Dividers
        ax.axvline(5.5, ymin=(y - row_h * 0.5) / 7, ymax=(y + row_h * 0.5) / 7,
                   color="#cccccc", lw=0.8, zorder=1)

    # Column line
    ax.axvline(5.5, color="#aaaaaa", lw=1.2, ymin=0.05, ymax=0.98)

    # Bottom note
    ax.text(6.5, 0.25,
            "Key finding: hook_p99_us_fapi_ul spikes to >7 000 µs during scheduler demotion — "
            "7× the slot budget — while standard metrics show only a minor MCS drop.",
            ha="center", va="center", fontsize=8, color="#333333", style="italic",
            bbox=dict(boxstyle="round,pad=0.3", fc="#fff3cd", ec="#e6ac00", alpha=0.9))

    plt.tight_layout()
    path = os.path.join(OUT, "fig_jbpf_vs_standard.png")
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=C["bg"])
    plt.close()
    print(f"Saved {path}")


# ══════════════════════════════════════════════════════════════════════════════
# Figure 5 — Dataset Overview
# ══════════════════════════════════════════════════════════════════════════════
def fig_dataset_overview():
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.patch.set_facecolor(C["bg"])
    fig.suptitle("Dataset Overview — Collected Scenarios and Labels",
                 fontsize=12, fontweight="bold", color=C["text"])

    # ── Left: class distribution ──────────────────────────────────────────
    ax = axes[0]
    ax.set_facecolor(C["bg"])
    classes = ["normal", "scheduler\nfault", "traffic\nflood", "channel\ndegradation"]
    counts = [2063, 462, 936, 2160]  # from combined_labelled.csv
    colors = ["#2e8b57", "#b22222", "#e65c00", "#1a6faf"]
    bars = ax.bar(classes, counts, color=colors, edgecolor="white", linewidth=1.2)
    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 30,
                str(count), ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_title("Class Distribution\n(combined_labelled.csv, n=5621)", fontsize=9)
    ax.set_ylabel("Samples (1-second windows)")
    ax.set_ylim(0, 2500)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)

    # ── Middle: stress scenario categories ───────────────────────────────
    ax = axes[1]
    ax.set_facecolor(C["bg"])
    cats = ["CPU/Memory\n(normal)", "Scheduling\n(sched_fault)", "Traffic\n(traffic_flood)", "Baseline\n(normal)"]
    cat_counts = [4, 7, 6, 6]
    cat_colors = ["#2e8b57", "#b22222", "#e65c00", "#2e8b57"]
    bars = ax.bar(cats, cat_counts, color=cat_colors, edgecolor="white", linewidth=1.2)
    for bar, count in zip(bars, cat_counts):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f"{count} scenarios", ha="center", va="bottom", fontsize=8)
    ax.set_title("Stress Anomaly Dataset\n(23 scenarios × ~120 s each)", fontsize=9)
    ax.set_ylabel("Number of scenarios")
    ax.set_ylim(0, 10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)

    # ── Right: channel scenario types ────────────────────────────────────
    ax = axes[2]
    ax.set_facecolor(C["bg"])
    ch_cats = ["Baseline\n(B1, B2)", "Time-varying\n(T1–T5)", "Steady\nImpairment\n(S1–S3)", "RLF Cycles\n(L1, L2)"]
    ch_counts = [2, 5, 3, 2]
    ch_labels = ["2 normal + degraded", "5 drive-by / mobility", "3 steady state", "2 RLF cycles"]
    ch_colors = ["#2e8b57", "#1a6faf", "#8b6914", "#6a0dad"]
    wedges, texts, autotexts = ax.pie(
        ch_counts, labels=ch_cats, autopct="%d", colors=ch_colors,
        startangle=90, pctdistance=0.65,
        wedgeprops=dict(edgecolor="white", linewidth=2)
    )
    for t in texts:
        t.set_fontsize(8)
    for at in autotexts:
        at.set_fontsize(8)
        at.set_color("white")
        at.set_fontweight("bold")
    ax.set_title("Channel Dataset\n(12 scenarios, realistic RF conditions)", fontsize=9)

    plt.tight_layout()
    path = os.path.join(OUT, "fig_dataset_overview.png")
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=C["bg"])
    plt.close()
    print(f"Saved {path}")


# ══════════════════════════════════════════════════════════════════════════════
# Figure 6 — CPU Overhead
# ══════════════════════════════════════════════════════════════════════════════
def fig_cpu_overhead():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    fig.patch.set_facecolor(C["bg"])
    fig.suptitle("jBPF CPU Overhead — Measured from jbpf_out_perf_list Telemetry",
                 fontsize=12, fontweight="bold", color=C["text"])

    hooks = [
        "rlc_ul_sdu_delivered", "rlc_ul_rx_pdu", "pdcp_ul_rx_data_pdu",
        "pdcp_ul_deliver_sdu", "fapi_ul_tti_request", "fapi_dl_tti_request",
        "rlc_dl_tx_pdu", "Other hooks (15)"
    ]
    cpu_pct = [0.731, 0.590, 0.554, 0.488, 0.435, 0.404, 0.058, 0.026]
    p99_us  = [8.31,  5.62,  6.30,  5.54,  6.40,  5.94,  10.53, None]

    colors_bar = [C["infra"] if v > 0.4 else C["data"] if v > 0.05 else "#aaaaaa"
                  for v in cpu_pct]

    # Left: CPU % bar chart
    ax1.set_facecolor(C["bg"])
    bars = ax1.barh(hooks[::-1], cpu_pct[::-1], color=colors_bar[::-1],
                    edgecolor="white", linewidth=1.0)
    for bar, pct in zip(bars, cpu_pct[::-1]):
        ax1.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height()/2,
                 f"{pct:.3f}%", va="center", fontsize=8.5, color=C["text"])
    ax1.axvline(3.29, color="#cc2222", lw=1.5, ls="--", alpha=0.7)
    ax1.text(3.31, 0.5, "Total:\n3.29%", color="#cc2222", fontsize=8,
             va="bottom")
    ax1.set_xlabel("CPU % of 1 core (@ 25 Mbps load)")
    ax1.set_title("Per-hook CPU overhead", fontsize=10)
    ax1.set_xlim(0, 1.0)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.tick_params(labelsize=7.5)

    # Right: p99 latency bar
    ax2.set_facecolor(C["bg"])
    p99_vals = [v if v is not None else 0 for v in p99_us[:-1]]
    bar_hooks = hooks[:-1]
    bars2 = ax2.barh(bar_hooks[::-1], p99_vals[::-1],
                     color=[C["infra"] if v > 8 else C["data"] for v in p99_vals[::-1]],
                     edgecolor="white", linewidth=1.0)
    for bar, v in zip(bars2, p99_vals[::-1]):
        ax2.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
                 f"{v:.2f} µs", va="center", fontsize=8.5)
    ax2.set_xlabel("p99 execution time (µs) — baseline clean channel")
    ax2.set_title("Per-hook p99 latency (steady-state baseline)", fontsize=10)
    ax2.axvline(1000, color="#aaaaaa", lw=0.8, ls=":", alpha=0.5)
    ax2.text(0.5, 0.02,
             "Note: During scheduler demotion anomaly, fapi_ul p99 reaches 7 289 µs (7× slot budget)",
             transform=ax2.transAxes, fontsize=7.5, color="#555555", style="italic", ha="center")
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.tick_params(labelsize=7.5)

    plt.tight_layout()
    path = os.path.join(OUT, "fig_cpu_overhead.png")
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=C["bg"])
    plt.close()
    print(f"Saved {path}")


# ══════════════════════════════════════════════════════════════════════════════
# Figure 7 — Protocol Stack Throughput (replaces ASCII in comparison doc)
# ══════════════════════════════════════════════════════════════════════════════
def fig_throughput_stack():
    fig, ax = plt.subplots(figsize=(10, 7))
    fig.patch.set_facecolor(C["bg"])
    ax.set_facecolor(C["bg"])
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title("Protocol Stack Overhead — Why Standard and Janus Throughput Differ",
                 fontsize=11, fontweight="bold", color=C["text"], pad=10)

    layers = [
        # (y_center, label, left_annotation, right_annotation, color)
        (6.1, "Application (iperf3)", "10.00 Mbps payload",     "← Janus measures here\n(iperf3 output)",   "#2e8b57"),
        (5.0, "IP + UDP",            "+28 bytes/packet",         "IP header (20) + UDP (8)",                  "#1a6faf"),
        (3.9, "GTP-U",               "+16 bytes/packet",         "GTP-U header + TEID",                       "#1a6faf"),
        (2.8, "PDCP",                "+3 bytes/PDU",             "PDCP header + integrity",                   "#6a0dad"),
        (1.7, "RLC",                 "+2 bytes/PDU",             "RLC AM header + segmentation",              "#6a0dad"),
        (0.6, "MAC Scheduler",       "19.45 Mbps total",         "← Standard measures here\n(MAC brate)",    "#b22222"),
    ]

    for y, label, left_ann, right_ann, color in layers:
        box(ax, 5.0, y, 4.0, 0.72, label, color=color, fontsize=9)
        ax.text(2.7, y, left_ann, ha="right", va="center", fontsize=8,
                color="#444444", bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#cccccc", alpha=0.8))
        ax.text(7.3, y, right_ann, ha="left", va="center", fontsize=7.5,
                color="#555555", style="italic")

    # Arrows between layers
    for i in range(len(layers) - 1):
        y1 = layers[i][0] - 0.36
        y2 = layers[i+1][0] + 0.36
        ax.annotate("", xy=(5.0, y2), xytext=(5.0, y1),
                    arrowprops=dict(arrowstyle="->", color="#888888", lw=1.5), zorder=2)

    # Ratio callout
    ax.text(1.5, 3.35, "~1.95×\nratio", ha="center", va="center", fontsize=11,
            fontweight="bold", color="#b22222",
            bbox=dict(boxstyle="round,pad=0.4", fc="#fff0f0", ec="#b22222", alpha=0.9))
    ax.annotate("", xy=(1.5, 0.95), xytext=(1.5, 2.9),
                arrowprops=dict(arrowstyle="<->", color="#b22222", lw=1.5), zorder=2)
    ax.annotate("", xy=(1.5, 5.75), xytext=(1.5, 3.8),
                arrowprops=dict(arrowstyle="<->", color="#b22222", lw=1.5), zorder=2)

    plt.tight_layout()
    path = os.path.join(OUT, "fig_throughput_stack.png")
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=C["bg"])
    plt.close()
    print(f"Saved {path}")


# ══════════════════════════════════════════════════════════════════════════════
# Figure 8 — Custom SINR Codelet Architecture
# ══════════════════════════════════════════════════════════════════════════════
def fig_custom_codelet():
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor(C["bg"])
    ax.set_facecolor(C["bg"])
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title("Custom SINR Codelet — In-Network Analytics Architecture",
                 fontsize=11, fontweight="bold", color=C["text"], pad=10)

    # gNB outer box
    gnb_bg = FancyBboxPatch((0.3, 1.2), 8.4, 5.4,
                             boxstyle="round,pad=0.1",
                             facecolor="#eef2ff", edgecolor=C["gnb"],
                             linewidth=2, alpha=0.9, zorder=1)
    ax.add_patch(gnb_bg)
    ax.text(4.5, 6.45, "srsRAN gNB  —  mac_sched_crc_indication hook",
            ha="center", va="center", fontsize=9, fontweight="bold", color=C["gnb"], zorder=2)

    # Hook codelet box
    box(ax, 4.5, 4.5, 7.6, 1.6,
        "mac_sched_crc_stats_custom.o  (hook codelet, fires on every UL CRC PDU)",
        color=C["jrtc"], fontsize=8.5)

    # Processing steps inside hook codelet (listed as text)
    steps = [
        "1. Extract SINR from ul_crc_pdu_indication",
        "2. Update min / max / sum / count  (basic stats)",
        "3. Accumulate sum_sq_sinr  (for variance: E[X²] − E[X]²)",
        "4. Update ring buffer[16]  (sliding window average)",
        "5. Compute variance and sliding_avg inline",
    ]
    for i, step in enumerate(steps):
        ax.text(1.0, 4.95 - i * 0.28, f"  {step}", ha="left", va="center",
                fontsize=7.2, color="white", zorder=4)

    # Maps
    box(ax, 3.0, 2.8, 3.0, 0.75, "stats_map_crc_custom",
        "Cleared each ~1 s window", color=C["data"], fontsize=8)
    box(ax, 6.6, 2.8, 3.0, 0.75, "sinr_window_map",
        "Ring buffer — persists always", color=C["gnb"], fontsize=8)

    ax.text(4.5, 3.55, "linked_maps (shared memory between codelets)",
            ha="center", va="center", fontsize=7.5, color="#555555", style="italic")

    # Collector codelet
    box(ax, 4.5, 1.75, 7.6, 0.75,
        "mac_stats_collect_custom.o  (collector codelet, runs on report_stats ~1 s tick)",
        color=C["data"], fontsize=8.5)
    ax.text(4.5, 1.55, "Reads stats_map → sets timestamp → sends via ringbuf → Protobuf serialiser → UDP",
            ha="center", va="center", fontsize=7.2, color="#333333")

    # Arrows inside gNB
    arrow(ax, 4.5, 3.72, 4.5, 3.38, color="#666666")
    arrow(ax, 3.0, 3.18, 3.0, 2.12, color=C["data"])
    arrow(ax, 6.6, 3.18, 6.6, 2.12, color=C["gnb"])
    arrow(ax, 4.5, 1.38, 4.5, 1.1, color=C["data"])

    # Output side
    box(ax, 10.5, 4.2, 1.6, 0.7, "InfluxDB\n:8086", color=C["infra"], fontsize=8.5)
    box(ax, 10.5, 2.8, 1.6, 0.7, "Grafana\n:3000", color=C["grafana"], fontsize=8.5)
    ax.text(10.5, 1.4, "New panels:\n• SINR variance\n• Sliding avg (N=16)",
            ha="center", va="center", fontsize=7.5, color=C["text"])
    arrow(ax, 8.7, 1.75, 9.7, 4.2, color=C["data"], label="UDP\nProtobuf", label_offset=(0.1, 0))
    arrow(ax, 10.5, 3.85, 10.5, 3.15, color=C["data"])
    arrow(ax, 10.5, 2.45, 10.5, 1.85, color=C["grafana"])

    plt.tight_layout()
    path = os.path.join(OUT, "fig_custom_codelet.png")
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=C["bg"])
    plt.close()
    print(f"Saved {path}")


if __name__ == "__main__":
    print("Generating architecture diagrams...")
    fig_system_architecture()
    fig_telemetry_flow()
    fig_channel_broker()
    fig_jbpf_vs_standard()
    fig_dataset_overview()
    fig_cpu_overhead()
    fig_throughput_stack()
    fig_custom_codelet()
    print("All diagrams generated in docs/figures/")
