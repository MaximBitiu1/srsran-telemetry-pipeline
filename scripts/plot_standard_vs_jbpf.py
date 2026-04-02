#!/usr/bin/env python3
"""
plot_standard_vs_jbpf.py
========================
Side-by-side comparison of what the standard srsRAN Grafana dashboard
shows vs what our jBPF pipeline captures, for three scenarios:

  1. sched_demote_rt_batch  — infrastructure fault invisible to standard monitoring
  2. traffic_flood_100m     — congestion: both see it, jBPF adds resolution
  3. T1 driveby_vehicular   — channel degradation: both see it, jBPF adds depth

Standard srsRAN dashboard (home.json) queries a single 'ue' table with:
  dl_mcs, pusch_snr_db, bsr, dl_nof_ok, dl_nof_nok, ul_brate, dl_brate, cqi
All single scalar values per second — no min/max, no hooks, no RLC/PDCP.

We simulate the standard view by stripping our jBPF data down to those same
single-value fields, then show what jBPF additionally reveals.

Output: docs/anomaly_report_figures/fig_standard_vs_jbpf_<scenario>.png
        docs/anomaly_report_figures/fig_standard_vs_jbpf_summary.png
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

REPO     = Path(__file__).resolve().parent.parent
STRESS   = REPO / "datasets/stress_anomaly/csv"
CHANNEL  = REPO / "datasets/channel/csv"
OUT_DIR  = REPO / "docs/anomaly_report_figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── colour palette ──────────────────────────────────────────────────────────
C_STD  = "#4878CF"   # blue  — standard monitoring
C_JBPF = "#D65F5F"   # red   — jBPF
C_FILL = "#FFCCCC"   # light red fill for envelope

# ── loaders ─────────────────────────────────────────────────────────────────

def load_stress(scenario_id: int) -> dict:
    harq = pd.read_csv(STRESS / "harq_stats.csv")
    bsr  = pd.read_csv(STRESS / "bsr_stats.csv")
    crc  = pd.read_csv(STRESS / "crc_stats.csv")
    perf = pd.read_csv(STRESS / "jbpf_out_perf_list.csv")
    rlc  = pd.read_csv(STRESS / "rlc_ul_stats.csv")

    return dict(
        harq = harq[harq.scenario_id == scenario_id],
        bsr  = bsr [bsr .scenario_id == scenario_id],
        crc  = crc [crc .scenario_id == scenario_id],
        fapi = perf[(perf.scenario_id == scenario_id) &
                    (perf.hook_name == "fapi_ul_tti_request")],
        rlc  = rlc [(rlc .scenario_id == scenario_id) &
                    (rlc .rb_id == 1) & (rlc.is_srb == 0)],
        label = harq[harq.scenario_id == scenario_id]["label"].iloc[0]
              if len(harq[harq.scenario_id == scenario_id]) else str(scenario_id),
    )


def load_channel(scenario_id: str) -> dict:
    harq = pd.read_csv(CHANNEL / "harq_stats.csv")
    bsr  = pd.read_csv(CHANNEL / "bsr_stats.csv")
    crc  = pd.read_csv(CHANNEL / "crc_stats.csv")
    perf = pd.read_csv(CHANNEL / "jbpf_out_perf_list.csv")
    rlc  = pd.read_csv(CHANNEL / "rlc_ul_stats.csv")

    return dict(
        harq = harq[harq.scenario_id == scenario_id],
        bsr  = bsr [bsr .scenario_id == scenario_id],
        crc  = crc [crc .scenario_id == scenario_id],
        fapi = perf[(perf.scenario_id == scenario_id) &
                    (perf.hook_name == "fapi_ul_tti_request")],
        rlc  = rlc [(rlc .scenario_id == scenario_id) &
                    (rlc .rb_id == 1) & (rlc.is_srb == 0)],
        label = harq[harq.scenario_id == scenario_id]["label"].iloc[0]
              if len(harq[harq.scenario_id == scenario_id]) else scenario_id,
    )


# ── per-scenario figure ──────────────────────────────────────────────────────

def plot_comparison(d: dict, out_path: Path, scenario_title: str, anomaly_note: str):
    """
    4-column × 2-row figure.
    Top row    = Standard srsRAN view  (single avg values, as in home.json)
    Bottom row = jBPF view             (full detail — min/max envelope + hooks)
    """
    harq = d["harq"].sort_values("relative_s")
    bsr  = d["bsr"] .sort_values("relative_s")
    crc  = d["crc"] .sort_values("relative_s")
    fapi = d["fapi"].sort_values("relative_s")
    rlc  = d["rlc"] .sort_values("relative_s")

    fig = plt.figure(figsize=(18, 9))
    fig.suptitle(scenario_title, fontsize=13, fontweight="bold", y=0.99)

    # Subtitle labels for each row
    fig.text(0.01, 0.97, "Standard srsRAN Grafana  (home.json — single scalar per second)",
             fontsize=9, color=C_STD, fontweight="bold", va="top")
    fig.text(0.01, 0.50, "jBPF eBPF Pipeline  (min/max envelopes + hook latency + RLC delay)",
             fontsize=9, color=C_JBPF, fontweight="bold", va="top")

    gs = gridspec.GridSpec(2, 4, figure=fig, hspace=0.55, wspace=0.35,
                           top=0.91, bottom=0.08)

    # ── helper ────────────────────────────────────────────────────────────────
    def _ax(row, col, ylabel, title, note=None):
        ax = fig.add_subplot(gs[row, col])
        ax.set_title(title, fontsize=8.5)
        ax.set_ylabel(ylabel, fontsize=8)
        ax.set_xlabel("Time (s)", fontsize=7)
        ax.tick_params(labelsize=7)
        if note:
            ax.annotate(note, xy=(0.5, 0.90), xycoords="axes fraction",
                        ha="center", fontsize=7, color="grey",
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.8))
        return ax

    # ── Row 0: Standard view ─────────────────────────────────────────────────
    # Col 0: DL MCS (single avg)
    ax = _ax(0, 0, "MCS", "DL MCS  [standard: avg only]")
    if not harq.empty:
        # Aggregate two MIMO streams → single avg (exactly what standard shows)
        mcs_std = harq.groupby("relative_s")["avg_mcs"].mean()
        ax.plot(mcs_std.index, mcs_std.values, color=C_STD, lw=1.0)
        ax.set_ylim(0, 30)

    # Col 1: UL SINR (single avg)
    ax = _ax(0, 1, "SINR (dB)", "UL SNR  [standard: pusch_snr_db]")
    if not crc.empty:
        ax.plot(crc.relative_s, crc.avg_sinr, color=C_STD, lw=1.0)

    # Col 2: BSR
    ax = _ax(0, 2, "BSR (KB)", "UL Buffer  [standard: bsr]")
    if not bsr.empty:
        ax.plot(bsr.relative_s, bsr.bytes / 1024, color=C_STD, lw=1.0)
        ax.set_ylim(bottom=0)

    # Col 3: DL BLER
    ax = _ax(0, 3, "BLER (%)", "DL BLER  [standard: dl_nof_nok/(ok+nok)]")
    if not crc.empty:
        bler = 100 * crc.harq_failure / crc.cnt_tx.replace(0, np.nan)
        ax.plot(crc.relative_s, bler.fillna(0), color=C_STD, lw=1.0)
        ax.set_ylim(bottom=0)

    # ── Row 1: jBPF view ─────────────────────────────────────────────────────
    # Col 0: MCS with min/max envelope
    ax = _ax(1, 0, "MCS", "DL MCS  [jBPF: avg ± min/max per slot]")
    if not harq.empty:
        # Per second: two streams — take min of mcs_min and max of mcs_max
        mcs_avg = harq.groupby("relative_s")["avg_mcs"].mean()
        mcs_min = harq.groupby("relative_s")["mcs_min"].min()
        mcs_max = harq.groupby("relative_s")["mcs_max"].max()
        t = mcs_avg.index
        ax.fill_between(t, mcs_min, mcs_max, alpha=0.3, color=C_FILL, label="min-max range")
        ax.plot(t, mcs_avg, color=C_JBPF, lw=1.0, label="avg")
        ax.set_ylim(0, 30)
        ax.legend(fontsize=6, loc="lower right")

    # Col 1: SINR with min/max envelope
    ax = _ax(1, 1, "SINR (dB)", "UL SINR  [jBPF: avg ± min/max per second]")
    if not crc.empty:
        ax.fill_between(crc.relative_s, crc.min_sinr, crc.max_sinr,
                        alpha=0.3, color=C_FILL, label="min-max range")
        ax.plot(crc.relative_s, crc.avg_sinr, color=C_JBPF, lw=1.0, label="avg")
        ax.legend(fontsize=6, loc="lower right")

    # Col 2: FAPI-UL hook p99 latency — NOT available in standard
    ax = _ax(1, 2, "p99 (µs)", "Hook Latency  [jBPF ONLY — no standard equivalent]",
             note="[NOT IN STANDARD DASHBOARD]")
    if not fapi.empty:
        ax.plot(fapi.relative_s, fapi.p99_us, color=C_JBPF, lw=0.9)
        ax.fill_between(fapi.relative_s, 0, fapi.p99_us, alpha=0.25, color=C_JBPF)

    # Col 3: RLC SDU max delivery latency — NOT available in standard
    ax = _ax(1, 3, "Latency (µs)", "RLC SDU Delay  [jBPF ONLY — no standard equivalent]",
             note="[NOT IN STANDARD DASHBOARD]")
    if not rlc.empty:
        ax.plot(rlc.relative_s, rlc.sdu_delivered_lat_max_us, color=C_JBPF, lw=0.9)
        ax.fill_between(rlc.relative_s, 0, rlc.sdu_delivered_lat_max_us,
                        alpha=0.25, color=C_JBPF)

    # Anomaly note box
    if anomaly_note:
        fig.text(0.5, 0.005, anomaly_note, ha="center", fontsize=8.5,
                 style="italic", color="#555555",
                 bbox=dict(boxstyle="round,pad=0.3", fc="#FFFBE6", ec="#CCAA00"))

    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out_path.name}")


# ── summary 3-panel figure ───────────────────────────────────────────────────

def plot_summary(out_path: Path):
    """
    3-column figure showing the 'invisible anomaly' for the scheduler demotion
    scenario: standard metrics look normal, jBPF hook latency is clearly anomalous.
    """
    perf = pd.read_csv(STRESS / "jbpf_out_perf_list.csv")
    crc  = pd.read_csv(STRESS / "crc_stats.csv")
    bsr  = pd.read_csv(STRESS / "bsr_stats.csv")

    baseline   = 0
    demote     = 12   # sched_demote_rt_batch (103× hook spike)
    traffic    = 15   # traffic_flood_100m

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle("Standard srsRAN Monitoring vs jBPF — The Invisible Anomaly",
                 fontsize=12, fontweight="bold")

    scenarios = [
        (baseline, "00 — Baseline (clean)",       "normal"),
        (demote,   "12 — Scheduler demotion",      "scheduler_fault"),
        (traffic,  "15 — Traffic flood 100 Mbps",  "traffic_flood"),
    ]

    for ax, (sid, title, cls) in zip(axes, scenarios):
        fapi = perf[(perf.scenario_id == sid) &
                    (perf.hook_name == "fapi_ul_tti_request")].sort_values("relative_s")
        c    = crc [crc .scenario_id == sid].sort_values("relative_s")
        b    = bsr [bsr .scenario_id == sid].sort_values("relative_s")

        ax2  = ax.twinx()

        # Standard: SINR (what standard Grafana shows)
        if not c.empty:
            ax.plot(c.relative_s, c.avg_sinr, color=C_STD, lw=1.2,
                    label="SINR avg (standard)", zorder=3)
        # Standard: BSR
        if not b.empty:
            bsr_kb = b.bytes / 1024
            ax.plot(b.relative_s, bsr_kb / bsr_kb.max() * c.avg_sinr.max() if not c.empty else bsr_kb,
                    color=C_STD, lw=1.0, ls="--", alpha=0.6,
                    label="BSR norm. (standard)", zorder=3)

        # jBPF: hook p99
        if not fapi.empty:
            ax2.fill_between(fapi.relative_s, 0, fapi.p99_us,
                             color=C_JBPF, alpha=0.35, zorder=2)
            ax2.plot(fapi.relative_s, fapi.p99_us, color=C_JBPF, lw=1.2,
                     label=f"Hook p99 (jBPF)", zorder=4)
            ax2.set_ylabel("Hook p99 (µs)", color=C_JBPF, fontsize=8)
            ax2.tick_params(axis="y", labelcolor=C_JBPF, labelsize=7)

        ax.set_title(title, fontsize=9, fontweight="bold")
        ax.set_xlabel("Time (s)", fontsize=8)
        ax.set_ylabel("SINR (dB) / normalised BSR", color=C_STD, fontsize=8)
        ax.tick_params(axis="y", labelcolor=C_STD, labelsize=7)
        ax.tick_params(axis="x", labelsize=7)

        # Legend
        lines1, lbl1 = ax.get_legend_handles_labels()
        lines2, lbl2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, lbl1 + lbl2, fontsize=6.5, loc="upper right")

        # Annotation for scheduler fault
        if sid == demote and not fapi.empty:
            peak_t = fapi.loc[fapi.p99_us.idxmax(), "relative_s"]
            peak_v = fapi.p99_us.max()
            ax2.annotate(f"7 289 µs\n(103× baseline)",
                         xy=(peak_t, peak_v),
                         xytext=(peak_t - 20, peak_v * 0.85),
                         fontsize=7, color=C_JBPF, fontweight="bold",
                         arrowprops=dict(arrowstyle="->", color=C_JBPF))

        if sid == baseline:
            ax.text(0.5, 0.03, "Both views: nothing anomalous",
                    transform=ax.transAxes, ha="center", fontsize=7.5,
                    color="#444", style="italic")
        elif sid == demote:
            ax.text(0.5, 0.03,
                    "Standard: SINR normal, BSR normal → no anomaly visible\njBPF: 7 289 µs hook spike → scheduler fault detected",
                    transform=ax.transAxes, ha="center", fontsize=7,
                    color="#444", style="italic")
        elif sid == traffic:
            ax.text(0.5, 0.03,
                    "Standard: BSR elevated (visible)\njBPF: confirms + hook stays flat → traffic, not scheduler",
                    transform=ax.transAxes, ha="center", fontsize=7,
                    color="#444", style="italic")

    plt.tight_layout()
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out_path.name}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Generating standard vs jBPF comparison plots...")

    # 1. Scheduler demotion — infrastructure fault invisible to standard monitoring
    d = load_stress(12)
    plot_comparison(
        d,
        OUT_DIR / "fig_standard_vs_jbpf_scheduler_fault.png",
        "Scenario 12 — sched_demote_rt_batch  |  Standard srsRAN Grafana  vs  jBPF Pipeline",
        "Standard monitoring shows normal SINR and BLER → anomaly is invisible. "
        "jBPF reveals 7 289 µs hook latency spike (103× baseline) — a scheduler priority demotion fault.",
    )

    # 2. Traffic flood — congestion visible in both but jBPF adds hook confirmation
    d = load_stress(15)
    plot_comparison(
        d,
        OUT_DIR / "fig_standard_vs_jbpf_traffic_flood.png",
        "Scenario 15 — traffic_flood_100m  |  Standard srsRAN Grafana  vs  jBPF Pipeline",
        "Both views show BSR elevation. jBPF additionally confirms hook latency stays flat "
        "→ congestion is application-layer, not scheduler stall. Standard cannot make this distinction.",
    )

    # 3. Channel degradation — both show it, jBPF adds SINR envelope + RLC delay
    d = load_channel("T1")
    plot_comparison(
        d,
        OUT_DIR / "fig_standard_vs_jbpf_channel_degradation.png",
        "Scenario T1 — driveby_vehicular_epa  |  Standard srsRAN Grafana  vs  jBPF Pipeline",
        "Channel degradation is visible in both. jBPF additionally reveals the per-second MCS and SINR "
        "min/max envelope (hidden by averaging in standard) and per-bearer RLC delivery delay.",
    )

    # 4. Summary — the 'invisible anomaly' in one figure
    plot_summary(OUT_DIR / "fig_standard_vs_jbpf_summary.png")

    print(f"\nAll figures saved to {OUT_DIR}/")


if __name__ == "__main__":
    main()
