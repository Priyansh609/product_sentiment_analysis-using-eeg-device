"""
MindWave Visualizer — Feature Extraction
==========================================
Converts raw, high-frequency per-session recordings (thousands of rows,
one per raw EEG sample) into a single small feature table (one row per
labeled trial) suitable for training a per-participant Random Forest.

This is the "squashing" step: it does NOT change or overwrite your raw
recordings in data/recordings/ — those stay exactly as recorded, forever,
as your audit trail. It only READS them and APPENDS new trial-level rows
to data/features/all_features.csv.

Usage
-----
    python extract_features.py
    python extract_features.py --participant P001
    python extract_features.py --recordings-dir path/to/recordings

How trials are detected
------------------------
A neuromarketing-mode CSV stamps `product_name` and `label` onto every
row while an experiment is active, and leaves them blank otherwise (see
dashboard.py's `_on_data`). This script walks each file and groups
consecutive rows into a "trial" whenever (product_name, label) is
non-blank and unchanged. Rows where product_name/label are blank (idle
recording, no active experiment) are skipped entirely — they carry no
label and are not useful for supervised training.

Participant ID
--------------
Your recorder filenames don't currently include participant_id, and
CSV_COLUMNS doesn't have a participant_id column either. Until that's
added (see the note printed at the end of this script), participant_id
is taken from the filename via --participant, or from a
`participant_id` column in the CSV if present, or defaults to
"UNKNOWN". Recommended fix: add a participant_id column to config.py's
CSV_COLUMNS and NEURO_CSV_COLUMNS, and have the dashboard prompt for
and stamp it, the same way product_name/label are stamped.

Only standard-library + pandas is used (already in your requirements.txt).
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

import pandas as pd
import numpy as np

# ── Column groups ────────────────────────────────────────────────────────

# Fields that come from the ~1 Hz ASIC/eSense stream. May be blank (NaN)
# for rows recorded before the first real reading — dropna() before
# aggregating so a handful of leading NaNs don't turn a mean into NaN.
METRIC_COLS = [
    "attention", "meditation",
    "delta", "theta", "low_alpha", "high_alpha",
    "low_beta", "high_beta", "low_gamma", "high_gamma",
]

BAND_COLS = [
    "delta", "theta", "low_alpha", "high_alpha",
    "low_beta", "high_beta", "low_gamma", "high_gamma",
]


def find_trials(df: pd.DataFrame) -> list[pd.DataFrame]:
    """
    Split a raw session dataframe into a list of per-trial dataframes.

    A trial is a maximal run of consecutive rows sharing the same
    non-blank (product_name, label) pair. Rows with a blank product_name
    or label (idle / no active experiment) are excluded.
    """
    df = df.copy()
    df["product_name"] = df["product_name"].fillna("")
    df["label"] = df["label"].fillna("")

    has_label = (df["product_name"] != "") & (df["label"] != "")

    # Assign a new group id every time (product_name, label) changes
    key = df["product_name"] + "\x00" + df["label"]
    group_id = (key != key.shift()).cumsum()

    trials = []
    for gid, group in df[has_label].groupby(group_id[has_label]):
        trials.append(group)
    return trials


def extract_trial_features(trial: pd.DataFrame, participant_id: str,
                            source_file: str) -> dict:
    """Compute one summary feature row for a single trial's raw rows."""
    # Only rows with usable signal quality contribute to averages —
    # signal_quality == 200 means no scalp contact (see packet_decoder.py).
    good = trial[trial["signal_quality"] < 200]
    if good.empty:
        good = trial  # fall back rather than silently dropping the trial

    feat: dict = {
        "participant_id": participant_id,
        "product_name":   trial["product_name"].iloc[0],
        "label":          trial["label"].iloc[0],
        "source_file":    source_file,
        "n_raw_rows":     len(trial),
        "n_good_rows":    len(good),
        "duration_s":     round(
            (pd.to_datetime(trial["timestamp"].iloc[-1])
             - pd.to_datetime(trial["timestamp"].iloc[0])).total_seconds(),
            2,
        ),
    }

    # Mean / std of eSense metrics and band powers (NaN-safe)
    for col in METRIC_COLS:
        series = pd.to_numeric(good[col], errors="coerce").dropna()
        feat[f"{col}_mean"] = round(series.mean(), 2) if len(series) else np.nan
        feat[f"{col}_std"]  = round(series.std(), 2)  if len(series) > 1 else 0.0

    # Beta / alpha ratio — same formula as eeg_processor.py's calculate()
    low_beta  = feat.get("low_beta_mean")  or 0
    high_beta = feat.get("high_beta_mean") or 0
    low_alpha  = feat.get("low_alpha_mean")  or 0
    high_alpha = feat.get("high_alpha_mean") or 0
    alpha_sum = max(low_alpha + high_alpha, 1)
    feat["beta_alpha_ratio"] = round(
        min((low_beta + high_beta) / alpha_sum * 100, 100), 2
    )

    # Blink count and rate — blink_strength is only non-blank on the
    # single row where a blink was detected (see packet_decoder.py),
    # so count non-null entries rather than averaging them.
    blink_series = pd.to_numeric(trial["blink_strength"], errors="coerce")
    n_blinks = int(blink_series.notna().sum())
    feat["blink_count"] = n_blinks
    feat["blink_rate_per_min"] = (
        round(n_blinks / (feat["duration_s"] / 60), 2)
        if feat["duration_s"] > 0 else 0.0
    )

    # Engagement score as recorded live, averaged over the trial
    if "engagement_score" in trial.columns:
        eng = pd.to_numeric(trial["engagement_score"], errors="coerce").dropna()
        feat["engagement_score_mean"] = round(eng.mean(), 2) if len(eng) else np.nan

    return feat


def infer_participant_id(filepath: str, explicit: str | None) -> str:
    """
    Determine participant_id for a file.

    Priority: --participant flag > participant_id embedded in filename
    (e.g. neuro_P001_2026-...csv) > "UNKNOWN".
    """
    if explicit:
        return explicit

    basename = os.path.basename(filepath)
    parts = basename.replace(".csv", "").split("_")
    for part in parts:
        if part.upper().startswith("P") and part[1:].isdigit():
            return part.upper()

    return "UNKNOWN"


def process_file(filepath: str, participant_id: str | None) -> list[dict]:
    """Read one raw CSV and return a list of trial feature dicts."""
    df = pd.read_csv(filepath)

    required = {"product_name", "label"}
    if not required.issubset(df.columns):
        print(f"  Skipping {filepath} — not a neuromarketing-mode CSV "
              f"(missing {required - set(df.columns)})")
        return []

    pid = infer_participant_id(filepath, participant_id)
    trials = find_trials(df)

    if not trials:
        print(f"  {os.path.basename(filepath)}: no labeled trials found "
              f"(experiment may not have been started, or file is idle-only)")
        return []

    results = []
    for trial in trials:
        feat = extract_trial_features(trial, pid, os.path.basename(filepath))
        results.append(feat)
        print(f"  {os.path.basename(filepath)}: trial "
              f"'{feat['product_name']}' -> {feat['label']} "
              f"({feat['n_raw_rows']} raw rows, {feat['duration_s']}s)")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recordings-dir", default="data/recordings",
        help="Directory containing raw session CSVs (default: data/recordings)",
    )
    parser.add_argument(
        "--output", default="data/features/all_features.csv",
        help="Path to the combined feature table (default: data/features/all_features.csv)",
    )
    parser.add_argument(
        "--participant", default=None,
        help="Force participant_id for ALL files processed this run "
             "(overrides filename-based detection)",
    )
    parser.add_argument(
        "--pattern", default="neuro_*.csv",
        help="Glob pattern for which files to process (default: neuro_*.csv — "
             "only neuromarketing-mode recordings have product_name/label)",
    )
    args = parser.parse_args()

    search_path = os.path.join(args.recordings_dir, args.pattern)
    files = sorted(glob.glob(search_path))

    if not files:
        print(f"No files matched {search_path}")
        sys.exit(1)

    print(f"Found {len(files)} file(s) to process:\n")

    all_rows: list[dict] = []
    for filepath in files:
        all_rows.extend(process_file(filepath, args.participant))

    if not all_rows:
        print("\nNo labeled trials extracted from any file. Nothing to write.")
        sys.exit(0)

    new_df = pd.DataFrame(all_rows)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    if os.path.exists(args.output):
        existing = pd.read_csv(args.output)
        # Avoid re-adding trials already extracted from a file processed before
        existing_keys = set(
            zip(existing.get("source_file", []), existing.get("participant_id", []),
                existing.get("product_name", []), existing.get("label", []))
        )
        before = len(new_df)
        new_df = new_df[~new_df.apply(
            lambda r: (r["source_file"], r["participant_id"],
                       r["product_name"], r["label"]) in existing_keys,
            axis=1,
        )]
        skipped = before - len(new_df)
        if skipped:
            print(f"\nSkipped {skipped} trial(s) already present in {args.output}")

        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_csv(args.output, index=False)

    print(f"\nWrote {len(new_df)} new trial row(s).")
    print(f"Feature table now has {len(combined)} total trial(s) "
          f"across {combined['participant_id'].nunique()} participant(s).")
    print(f"-> {args.output}")

    if "UNKNOWN" in combined["participant_id"].values:
        print(
            "\nNOTE: some rows have participant_id='UNKNOWN' because it could not "
            "be inferred from the filename (expected a 'P###' segment, e.g. "
            "neuro_P001_2026-...csv) and --participant wasn't given.\n"
            "Recommended: add a participant_id column to config.py's CSV_COLUMNS "
            "and NEURO_CSV_COLUMNS, and have the dashboard stamp it per-row like "
            "product_name/label already are — this removes the need to guess "
            "participant identity from filenames at all."
        )


if __name__ == "__main__":
    main()