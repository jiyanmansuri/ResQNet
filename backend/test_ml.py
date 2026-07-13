"""
test_ml.py — Smoke tests and validation checks for the XGBoost ML Engine.
Run this script to ensure model files are present and loading correctly.
"""

import os
import sys

# Ensure backend directory is in python path
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_DIR)

try:
    from ml_model import predict, MODEL_PATH, FEATURES_PATH
    print("✅ Successfully imported ml_model module.")
except ImportError as err:
    print(f"❌ Failed to import ml_model: {err}")
    sys.exit(1)

def run_tests():
    print("=" * 60)
    print("  ResQNet ML Validation Suite")
    print("=" * 60)

    # 1. Check if model files exist
    print("[1/3] Checking persisted artifact files...")
    if not os.path.exists(MODEL_PATH):
        print(f"❌ MODEL NOT FOUND: {MODEL_PATH}")
        print("Please run 'python ml_model.py' to train and save the model.")
        sys.exit(1)
    if not os.path.exists(FEATURES_PATH):
        print(f"❌ FEATURES SPEC NOT FOUND: {FEATURES_PATH}")
        print("Please run 'python ml_model.py' to train and save the model.")
        sys.exit(1)
    print("✅ Persistent model artifacts found.")

    # 2. Run predictions and check ranges
    print("\n[2/3] Validating prediction outputs...")
    test_cases = [
        {
            "description": "High flood level + Active SOS (Critical)",
            "data": {
                "flood_level": 8.8,
                "air_quality": 360,
                "sos_active": 1,
                "distance_from_epicenter": 1.5,
                "num_sos_nearby": 5,
                "battery": 20,
            },
            "expected_severity": "Critical"
        },
        {
            "description": "Moderate flood level (Serious)",
            "data": {
                "flood_level": 5.5,
                "air_quality": 180,
                "sos_active": 0,
                "distance_from_epicenter": 10.0,
                "num_sos_nearby": 2,
                "battery": 80,
            },
            "expected_severity": "Serious"
        },
        {
            "description": "Normal parameters (Stable)",
            "data": {
                "flood_level": 0.5,
                "air_quality": 80,
                "sos_active": 0,
                "distance_from_epicenter": 45.0,
                "num_sos_nearby": 0,
                "battery": 95,
            },
            "expected_severity": "Stable"
        }
    ]

    passed = 0
    for i, tc in enumerate(test_cases, 1):
        print(f"\n  Running Test Case {i}: {tc['description']}...")
        try:
            res = predict(tc["data"])
            print(f"  -> Predicted: {res['severity']} (Confidence: {res['confidence']})")
            if res["severity"] == tc["expected_severity"]:
                print("  ✅ PASS")
                passed += 1
            else:
                print(f"  ❌ FAIL (Expected: {tc['expected_severity']}, got {res['severity']})")
        except Exception as exc:
            print(f"  ❌ EXCEPTION: {exc}")

    # 3. Final summary
    print("\n[3/3] Finalizing Validation Report...")
    print(f"Tests Completed: {len(test_cases)} | Passed: {passed} | Failed: {len(test_cases) - passed}")
    if passed == len(test_cases):
        print("\n🎉 ML Model is fully validated and ready for production inference!\n")
    else:
        print("\n⚠️ ML validation suite failed. Review the classification mappings.\n")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
