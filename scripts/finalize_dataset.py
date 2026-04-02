#!/usr/bin/env python3
"""
finalize_dataset.py
===================
Produces a single ML-ready dataset from the two cleaned feature matrices.

Steps:
  1. Assign 4-class labels
  2. Combine stress + channel datasets
  3. Fill NaN values
  4. Select feature columns
  5. Normalize (StandardScaler — fit on train only)
  6. Train/test split by scenario (not by row)
  7. Save outputs

Outputs in datasets/:
  combined_labelled.csv   — full dataset with class labels (pre-scaling)
  train_features.csv      — training set (normalised)
  test_features.csv       — test set (same scaler as train)
  feature_scaler.json     — mean + std per feature for inference
  class_map.json          — label integer → class name
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT  = REPO / "datasets"

# ── 1. Class label assignment ────────────────────────────────────────────────

# Stress scenario IDs (integers 0–22)
CLASS_STRESS = {
    "normal":          [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 21],
    "scheduler_fault": [12, 13, 14, 22],
    "traffic_flood":   [15, 16, 17, 18, 19, 20],
    # channel_degradation: none in stress dataset
}

# Channel scenario IDs (strings B1, B2, …)
CLASS_CHANNEL = {
    "normal":              ["B1", "S2"],
    "channel_degradation": ["B2", "T1", "T2", "S1", "L1",
                            "T3", "T4", "T5", "S3", "L2"],
    # scheduler_fault / traffic_flood: none in channel dataset
}

CLASS_NAMES  = ["normal", "scheduler_fault", "traffic_flood", "channel_degradation"]
CLASS_INT    = {n: i for i, n in enumerate(CLASS_NAMES)}

# ── 2. Feature columns to use ────────────────────────────────────────────────
# Only keep the most informative, non-redundant features.
# Excluded: raw byte counters (use derived _kb/_throughput instead),
#           mcs_count/tx counts (not informative on their own),
#           hook num (correlated with hook p99 but noisier).

FEATURE_COLS = [
    # Hook latency — primary novel signal
    "hook_p99_us_fapi_ul",
    "hook_p99_us_fapi_dl",
    "hook_p99_us_pdcp_ul_deliver",
    "hook_p99_us_pdcp_ul_rx",
    "hook_p99_us_rlc_ul_rx",
    "hook_p99_us_rlc_ul_deliver",
    "hook_p99_us_rlc_dl_tx",
    "hook_max_us_fapi_ul",       # max captures spike peaks better than p99
    # MAC / channel quality
    "harq_mcs_avg",
    "harq_mcs_min",
    "harq_cons_retx",
    "harq_fail_rate",
    # PHY
    "crc_sinr_avg",
    "crc_harq_fail",
    "crc_success_rate",
    # Buffer / congestion
    "bsr_kb",
    # RLC
    "rlc_throughput_kb",
    "rlc_lat_avg_us",
    "rlc_lat_max_us",
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def assign_labels(df: pd.DataFrame, class_map: dict) -> pd.DataFrame:
    df = df.copy()
    df["class_name"] = None
    for cls, ids in class_map.items():
        df.loc[df["scenario_id"].isin(ids), "class_name"] = cls
    df = df.dropna(subset=["class_name"])
    df["class_id"] = df["class_name"].map(CLASS_INT)
    return df


def fill_nans(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fill NaN values:
    - Hook latency NaN → 0  (hook didn't fire = no execution time measured)
    - MAC / PHY features NaN → 0  (no transmission scheduled in that second)
    - RLC features NaN → 0  (no data bearer active)
    Forward-fill first within each scenario to catch isolated gaps,
    then fill any remaining NaN with 0.
    """
    df = df.copy()
    df = df.sort_values(["scenario_id", "relative_s"])
    feature_cols_present = [c for c in FEATURE_COLS if c in df.columns]
    df[feature_cols_present] = (
        df.groupby("scenario_id")[feature_cols_present]
        .transform(lambda x: x.ffill().fillna(0))
    )
    return df


def standard_scale(train: pd.DataFrame, test: pd.DataFrame, feature_cols: list):
    """
    Fit StandardScaler on train, apply to both.
    Returns scaled train, scaled test, and scaler dict {col: {mean, std}}.
    """
    scaler = {}
    train = train.copy()
    test  = test.copy()
    for col in feature_cols:
        if col not in train.columns:
            continue
        mu  = train[col].mean()
        std = train[col].std()
        std = std if std > 0 else 1.0   # avoid div-by-zero for constant columns
        train[col] = (train[col] - mu) / std
        test[col]  = (test[col]  - mu) / std
        scaler[col] = {"mean": round(mu, 6), "std": round(std, 6)}
    return train, test, scaler


def scenario_train_test_split(df: pd.DataFrame, test_fraction: float = 0.2,
                               seed: int = 42):
    """
    Split by scenario_id within each class so every class is represented
    in both train and test.
    """
    rng = np.random.default_rng(seed)
    train_ids, test_ids = [], []

    for cls in CLASS_NAMES:
        cls_df = df[df["class_name"] == cls]
        scenarios = cls_df["scenario_id"].unique()
        n_test = max(1, round(len(scenarios) * test_fraction))
        chosen_test = rng.choice(scenarios, size=n_test, replace=False)
        test_ids.extend(chosen_test.tolist())
        train_ids.extend([s for s in scenarios if s not in chosen_test])

    train = df[df["scenario_id"].isin(train_ids)].copy()
    test  = df[df["scenario_id"].isin(test_ids)].copy()
    return train, test, train_ids, test_ids


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    stress  = pd.read_csv(REPO / "datasets/stress_anomaly/stress_features.csv")
    channel = pd.read_csv(REPO / "datasets/channel/channel_features.csv")

    # Tag source dataset
    stress["dataset"]  = "stress"
    channel["dataset"] = "channel"

    # Assign class labels
    stress_labelled  = assign_labels(stress,  CLASS_STRESS)
    channel_labelled = assign_labels(channel, CLASS_CHANNEL)

    # Combine
    combined = pd.concat([stress_labelled, channel_labelled], ignore_index=True)
    combined = combined.sort_values(["class_name", "scenario_id", "relative_s"])

    # Fill NaNs
    combined = fill_nans(combined)

    # Save pre-scaling labelled dataset
    combined_out_cols = ["scenario_id", "dataset", "label", "category",
                         "class_name", "class_id", "relative_s"] + \
                        [c for c in FEATURE_COLS if c in combined.columns]
    combined[combined_out_cols].to_csv(OUT / "combined_labelled.csv", index=False)

    # Train / test split by scenario
    train_df, test_df, train_ids, test_ids = scenario_train_test_split(combined)

    # Report split
    print("Train/test scenario split:")
    for cls in CLASS_NAMES:
        tr = [s for s in train_ids if s in combined[combined.class_name==cls].scenario_id.unique()]
        te = [s for s in test_ids  if s in combined[combined.class_name==cls].scenario_id.unique()]
        print(f"  {cls:25s}  train={tr}  test={te}")

    # Normalize
    feat_present = [c for c in FEATURE_COLS if c in combined.columns]
    train_scaled, test_scaled, scaler = standard_scale(train_df, test_df, feat_present)

    # Output columns
    out_cols = ["scenario_id", "dataset", "label", "category",
                "class_name", "class_id", "relative_s"] + feat_present

    train_scaled[out_cols].to_csv(OUT / "train_features.csv", index=False)
    test_scaled[out_cols].to_csv(OUT  / "test_features.csv",  index=False)

    # Save scaler
    with open(OUT / "feature_scaler.json", "w") as f:
        json.dump(scaler, f, indent=2)

    # Save class map
    with open(OUT / "class_map.json", "w") as f:
        json.dump({str(v): k for k, v in CLASS_INT.items()}, f, indent=2)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("  Final dataset summary")
    print("="*60)
    print(f"\n  combined_labelled.csv  : {len(combined[combined_out_cols])} rows × {len(combined_out_cols)} cols")
    print(f"  train_features.csv     : {len(train_scaled)} rows")
    print(f"  test_features.csv      : {len(test_scaled)} rows")
    print(f"  Features used          : {len(feat_present)}")
    print(f"\n  Class distribution (combined):")
    for cls, cid in CLASS_INT.items():
        n = len(combined[combined.class_name == cls])
        print(f"    {cid}  {cls:25s}  {n:5d} rows")
    print(f"\n  NaN remaining after fill: {combined[feat_present].isnull().sum().sum()}")
    print(f"\n  Saved to {OUT}/")


if __name__ == "__main__":
    main()
