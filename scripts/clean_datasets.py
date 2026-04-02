#!/usr/bin/env python3
"""
clean_datasets.py
=================
Produces one training-ready feature matrix per dataset:

  datasets/stress_anomaly/stress_features.csv
  datasets/channel/channel_features.csv

Each output has one row per (scenario_id, relative_s) with all
telemetry schemas merged and counters differenced.

Steps per dataset:
  1. harq_stats      — aggregate 2 MIMO streams → 1 row/s
  2. bsr_stats       — direct (already 1 row/s)
  3. crc_stats       — direct (already 1 row/s)
  4. jbpf_out_perf_list — pivot: one column per steady-state hook metric
  5. rlc_ul_stats    — keep data bearer (rb_id=1, is_srb=0),
                       diff cumulative counters within each scenario
  6. outer-join all on (scenario_id, relative_s)
  7. write csv
"""

import pandas as pd
import numpy as np
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Hooks that appear every second during steady-state operation
STEADY_HOOKS = [
    "fapi_ul_tti_request",
    "fapi_dl_tti_request",
    "pdcp_ul_deliver_sdu",
    "pdcp_ul_rx_data_pdu",
    "rlc_ul_rx_pdu",
    "rlc_ul_sdu_delivered",
    "rlc_dl_tx_pdu",
]

# Short names for output columns
HOOK_SHORT = {
    "fapi_ul_tti_request":  "fapi_ul",
    "fapi_dl_tti_request":  "fapi_dl",
    "pdcp_ul_deliver_sdu":  "pdcp_ul_deliver",
    "pdcp_ul_rx_data_pdu":  "pdcp_ul_rx",
    "rlc_ul_rx_pdu":        "rlc_ul_rx",
    "rlc_ul_sdu_delivered": "rlc_ul_deliver",
    "rlc_dl_tx_pdu":        "rlc_dl_tx",
}

# ────────────────────────────────────────────────────────────────────────────

def load(csv_dir: Path, name: str) -> pd.DataFrame:
    p = csv_dir / f"{name}.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p)


def clean_harq(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate two MIMO stream rows per second into one.
    avg_mcs → mean across streams
    mcs_min → min across streams
    mcs_max → max across streams
    cons_retx_max → max across streams (worst-case retransmission)
    mcs_count → sum (total slots sampled)
    """
    if df.empty:
        return df
    agg = (
        df.groupby(["scenario_id", "label", "category", "relative_s"], as_index=False)
        .agg(
            harq_mcs_avg     =("avg_mcs",        "mean"),
            harq_mcs_min     =("mcs_min",         "min"),
            harq_mcs_max     =("mcs_max",         "max"),
            harq_cons_retx   =("cons_retx_max",   "max"),
            harq_slots_sampled=("mcs_count",      "sum"),
        )
    )
    return agg


def clean_bsr(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.rename(columns={"bytes": "bsr_bytes", "cnt": "bsr_cnt"}) \
             .drop(columns=["timestamp_utc", "timestamp_unix", "duUeIndex"], errors="ignore")


def clean_crc(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.rename(columns={
        "avg_sinr":    "crc_sinr_avg",
        "min_sinr":    "crc_sinr_min",
        "max_sinr":    "crc_sinr_max",
        "cnt_sinr":    "crc_sinr_cnt",
        "cnt_tx":      "crc_tx",
        "succ_tx":     "crc_succ_tx",
        "harq_failure":"crc_harq_fail",
        "cons_max":    "crc_cons_fail_max",
    }).drop(columns=["timestamp_utc", "timestamp_unix", "duUeIndex"], errors="ignore")


def clean_perf(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only steady-state hooks; pivot to wide format.
    Output columns per hook (short name):
      hook_<name>_p99_us, hook_<name>_max_us, hook_<name>_num
    """
    if df.empty:
        return df

    steady = df[df["hook_name"].isin(STEADY_HOOKS)].copy()
    steady["hook_short"] = steady["hook_name"].map(HOOK_SHORT)

    # Pivot p99, max, num for each hook
    pivot = steady.pivot_table(
        index=["scenario_id", "label", "category", "relative_s"],
        columns="hook_short",
        values=["p99_us", "max_us", "num"],
        aggfunc="mean",   # should be unique per (scenario, second, hook)
    )
    pivot.columns = [f"hook_{m}_{h}" for m, h in pivot.columns]
    pivot = pivot.reset_index()
    return pivot


def clean_rlc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep data bearer (rb_id=1, is_srb=0).
    Diff cumulative byte counters within each scenario.
    """
    if df.empty:
        return df

    data = df[(df["rb_id"] == 1) & (df["is_srb"] == 0)].copy()
    data = data.sort_values(["scenario_id", "relative_s"])

    # Diff within each scenario — first row of each scenario gets NaN → fill 0
    data["rlc_bytes_per_s"] = (
        data.groupby("scenario_id")["sdu_delivered_bytes_total"]
        .diff()
        .clip(lower=0)     # guard against counter resets → never negative
        .fillna(0)
        .astype(int)
    )
    data["rlc_pdu_bytes_per_s"] = (
        data.groupby("scenario_id")["pdu_bytes_total"]
        .diff()
        .clip(lower=0)
        .fillna(0)
        .astype(int)
    )

    return data.rename(columns={
        "sdu_delivered_lat_avg_us": "rlc_lat_avg_us",
        "sdu_delivered_lat_max_us": "rlc_lat_max_us",
        "sdu_delivered_lat_count":  "rlc_lat_count",
    }).drop(columns=[
        "timestamp_utc", "timestamp_unix", "duUeIndex",
        "rb_id", "is_srb", "sdu_delivered_bytes_total", "pdu_bytes_total",
    ], errors="ignore")


def merge_all(parts: list[pd.DataFrame]) -> pd.DataFrame:
    """
    Outer-join all cleaned parts on (scenario_id, relative_s).
    label/category are filled from a lookup built across ALL parts so that
    hook-only scenarios (no harq/bsr/crc) still get their metadata.
    """
    # Build scenario metadata lookup from every part that has label/category
    meta_frames = []
    for part in parts:
        if part is None or part.empty:
            continue
        if "label" in part.columns and "category" in part.columns:
            meta_frames.append(
                part[["scenario_id", "label", "category"]]
                .dropna(subset=["label", "category"])
                .drop_duplicates("scenario_id")
            )
    meta = pd.concat(meta_frames).drop_duplicates("scenario_id") if meta_frames else pd.DataFrame()

    # Merge feature columns only (drop label/category from all parts)
    result = None
    for part in parts:
        if part is None or part.empty:
            continue
        part = part.drop(columns=["label", "category"], errors="ignore")
        if result is None:
            result = part
        else:
            result = result.merge(part, on=["scenario_id", "relative_s"], how="outer")

    # Re-attach metadata
    if not meta.empty:
        result = result.merge(meta, on="scenario_id", how="left")

    # Put metadata columns first
    front = ["scenario_id", "label", "category", "relative_s"]
    rest  = [c for c in result.columns if c not in front]
    result = result[front + rest]

    return result.sort_values(["scenario_id", "relative_s"]).reset_index(drop=True)


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a few derived columns that are directly useful for ML:
      harq_fail_rate  = crc_harq_fail / crc_tx  (per-slot failure fraction)
      crc_success_rate = crc_succ_tx / crc_tx
      bsr_kb          = bsr_bytes / 1024
      rlc_bytes_kb    = rlc_bytes_per_s / 1024
    """
    if "crc_harq_fail" in df.columns and "crc_tx" in df.columns:
        df["harq_fail_rate"] = (
            df["crc_harq_fail"] / df["crc_tx"].replace(0, np.nan)
        ).fillna(0).round(4)
        df["crc_success_rate"] = (
            df["crc_succ_tx"] / df["crc_tx"].replace(0, np.nan)
        ).fillna(0).round(4)

    if "bsr_bytes" in df.columns:
        df["bsr_kb"] = (df["bsr_bytes"] / 1024).round(2)

    if "rlc_bytes_per_s" in df.columns:
        df["rlc_throughput_kb"] = (df["rlc_bytes_per_s"] / 1024).round(2)

    return df


def print_summary(df: pd.DataFrame, name: str):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    print(f"  Shape        : {df.shape[0]} rows × {df.shape[1]} columns")
    print(f"  Scenarios    : {sorted(df['scenario_id'].unique().tolist())}")
    print(f"  NaN summary  :")
    nan_cols = df.isnull().sum()
    nan_cols = nan_cols[nan_cols > 0]
    if nan_cols.empty:
        print("    none")
    else:
        for col, n in nan_cols.items():
            pct = 100 * n / len(df)
            print(f"    {col:45s} {n:4d} ({pct:.0f}%)")
    print(f"\n  Columns      :")
    for c in df.columns:
        print(f"    {c}")


def process(csv_dir: Path, out_path: Path, name: str):
    harq  = load(csv_dir, "harq_stats")
    bsr   = load(csv_dir, "bsr_stats")
    crc   = load(csv_dir, "crc_stats")
    perf  = load(csv_dir, "jbpf_out_perf_list")
    rlc   = load(csv_dir, "rlc_ul_stats")

    parts = [
        clean_harq(harq),
        clean_bsr(bsr),
        clean_crc(crc),
        clean_perf(perf),
        clean_rlc(rlc),
    ]

    df = merge_all(parts)
    df = add_derived_features(df)
    df.to_csv(out_path, index=False)
    print_summary(df, name)
    print(f"\n  Saved → {out_path}")


def main():
    datasets = [
        (
            REPO / "datasets/stress_anomaly/csv",
            REPO / "datasets/stress_anomaly/stress_features.csv",
            "Stress anomaly dataset",
        ),
        (
            REPO / "datasets/channel/csv",
            REPO / "datasets/channel/channel_features.csv",
            "Realistic channel dataset",
        ),
    ]
    for csv_dir, out_path, name in datasets:
        process(csv_dir, out_path, name)


if __name__ == "__main__":
    main()
