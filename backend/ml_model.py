"""
ml_model.py — ResQNet ML Engine
Responsibilities:
  1. train_model()  — generate synthetic data, train XGBoost, persist artefacts
  2. predict()      — load artefacts and return severity classification
"""

import os
import warnings
warnings.filterwarnings("ignore")

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
from typing import Tuple, Dict, Any

# ──────────────────────────────────────────────
# Paths (relative to this file's directory)
# ──────────────────────────────────────────────
_DIR          = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH    = os.path.join(_DIR, "model.pkl")
FEATURES_PATH = os.path.join(_DIR, "features.pkl")

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
FEATURE_COLS = [
    "flood_level",
    "air_quality",
    "sos_active",
    "distance_from_epicenter",
    "num_sos_nearby",
    "battery",
]

SEVERITY_MAP = {2: "Critical", 1: "Serious", 0: "Stable"}


# ══════════════════════════════════════════════
# PART 1 — Training
# ══════════════════════════════════════════════

def _generate_dataset(n: int = 2000, seed: int = 42) -> pd.DataFrame:
    """
    Synthesise n disaster incident records with realistic distributions.
    Label assignment (priority order — first match wins):
      2  Critical : sos_active=1  AND  (flood_level > 7  OR  air_quality > 350)
      1  Serious  : sos_active=1  OR   flood_level > 5   OR  air_quality > 250
      0  Stable   : everything else
    """
    rng = np.random.default_rng(seed)

    df = pd.DataFrame({
        "flood_level"             : rng.uniform(0, 10, n).round(2),
        "air_quality"             : rng.integers(0, 501, n),
        "sos_active"              : rng.choice([0, 1], size=n, p=[0.80, 0.20]),
        "distance_from_epicenter" : rng.uniform(0, 50, n).round(3),
        "num_sos_nearby"          : rng.integers(0, 11, n),
        "battery"                 : rng.integers(0, 101, n),
    })

    # Label — vectorised, priority order
    critical_mask = (
        (df["sos_active"] == 1) &
        ((df["flood_level"] > 7) | (df["air_quality"] > 350))
    )
    serious_mask = (
        (df["sos_active"] == 1) |
        (df["flood_level"] > 5) |
        (df["air_quality"] > 250)
    )

    df["severity"] = 0                        # default: Stable
    df.loc[serious_mask,  "severity"] = 1     # Serious
    df.loc[critical_mask, "severity"] = 2     # Critical (overrides Serious)

    return df


def train_model() -> None:
    """
    Generate synthetic data, train XGBoostClassifier, print metrics,
    and persist model.pkl + features.pkl to the backend directory.
    """
    print("=" * 60)
    print("  ResQNet — XGBoost Model Training")
    print("=" * 60)

    # ── 1. Data generation ──────────────────────────────────────
    print("\n[1/4] Generating 2 000 synthetic disaster records …")
    df = _generate_dataset(n=2000)

    dist = df["severity"].value_counts().sort_index()
    print(f"      Label distribution -> "
          f"Stable={dist.get(0,0)}  "
          f"Serious={dist.get(1,0)}  "
          f"Critical={dist.get(2,0)}")

    X = df[FEATURE_COLS]
    y = df["severity"]

    # ── 2. Train / test split ────────────────────────────────────
    print("\n[2/4] Splitting 80 / 20 train-test …")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    # ── 3. Model training ────────────────────────────────────────
    print("\n[3/4] Training XGBoostClassifier …")
    print("      max_depth=4  n_estimators=100  use_label_encoder=False")

    model = XGBClassifier(
        max_depth        = 4,
        n_estimators     = 100,
        objective        = "multi:softprob",
        num_class        = 3,
        eval_metric      = "mlogloss",
        use_label_encoder= False,
        random_state     = 42,
        verbosity        = 0,
    )
    model.fit(X_train, y_train)

    # ── 4. Evaluation ────────────────────────────────────────────
    y_pred   = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)

    print(f"\n[4/4] Evaluation on test set ({len(X_test)} samples)")
    print(f"      Accuracy : {accuracy:.4f}  ({accuracy*100:.2f} %)")
    print("\n      Classification Report:")
    print(
        classification_report(
            y_test, y_pred,
            target_names=["Stable", "Serious", "Critical"],
        )
    )

    # ── 5. Persist artefacts ─────────────────────────────────────
    joblib.dump(model,       MODEL_PATH)
    joblib.dump(FEATURE_COLS, FEATURES_PATH)

    print(f"      model.pkl    -> {MODEL_PATH}")
    print(f"      features.pkl -> {FEATURES_PATH}")
    print("\n✅  Training complete.\n")


# ══════════════════════════════════════════════
# PART 2 — Inference
# ══════════════════════════════════════════════

# Module-level cache so artefacts are loaded only once per process lifetime
_model    = None
_features = None


def _load_artefacts() -> Tuple[Any, Any]:
    """Lazy-load model and feature list; raise if files are missing."""
    global _model, _features

    if _model is None or _features is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"model.pkl not found at {MODEL_PATH}. "
                "Run ml_model.py (or train_model()) first."
            )
        if not os.path.exists(FEATURES_PATH):
            raise FileNotFoundError(
                f"features.pkl not found at {FEATURES_PATH}. "
                "Run ml_model.py (or train_model()) first."
            )
        _model    = joblib.load(MODEL_PATH)
        _features = joblib.load(FEATURES_PATH)

    return _model, _features


def predict(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify a single sensor reading into a severity level.

    Parameters
    ----------
    sensor_data : dict
        Must contain keys: flood_level, air_quality, sos_active,
        distance_from_epicenter, num_sos_nearby, battery.

    Returns
    -------
    dict with keys:
        severity      : str  — "Critical" | "Serious" | "Stable"
        severity_code : int  — 2 | 1 | 0
        confidence    : float — highest class probability (0.0 – 1.0)
    """
    model, features = _load_artefacts()

    # Build a single-row DataFrame in the exact column order used at training
    try:
        row = pd.DataFrame([{col: sensor_data[col] for col in features}])
    except KeyError as missing:
        raise ValueError(
            f"sensor_data is missing required feature: {missing}. "
            f"Required keys: {features}"
        )

    # Predict class and probabilities
    severity_code  = int(model.predict(row)[0])
    probabilities  = model.predict_proba(row)[0]   # shape: (3,)
    confidence     = round(float(probabilities[severity_code]), 2)

    return {
        "severity"      : SEVERITY_MAP[severity_code],
        "severity_code" : severity_code,
        "confidence"    : confidence,
    }


# ══════════════════════════════════════════════
# PART 3 — Main guard
# ══════════════════════════════════════════════

if __name__ == "__main__":
    train_model()

    # Quick smoke-test of predict() right after training
    print("── Smoke-test: predict() ──────────────────────────────")
    samples = [
        {   # Should be Critical
            "flood_level": 8.5, "air_quality": 380, "sos_active": 1,
            "distance_from_epicenter": 2.1, "num_sos_nearby": 7, "battery": 22,
        },
        {   # Should be Serious
            "flood_level": 6.0, "air_quality": 180, "sos_active": 1,
            "distance_from_epicenter": 15.0, "num_sos_nearby": 3, "battery": 55,
        },
        {   # Should be Stable
            "flood_level": 1.2, "air_quality": 95, "sos_active": 0,
            "distance_from_epicenter": 40.0, "num_sos_nearby": 0, "battery": 90,
        },
    ]

    for i, sample in enumerate(samples, 1):
        result = predict(sample)
        print(
            f"  Sample {i}: {result['severity']:<10} "
            f"(code={result['severity_code']}, confidence={result['confidence']})"
        )

    print("\n✅  Smoke-test passed.\n")
