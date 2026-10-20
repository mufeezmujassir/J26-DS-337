"""Demo runner for Consensus Level and Fairness Metrics (Step 10e).

Displays:
1. Comparative consensus metrics across methods for demo groups in
   data/processed/decision_demo_groups.json:
   - Primary winner or compromise plan
   - Mean acceptance
   - Min acceptance
   - Consensus level & label
   - Consensus reached (True/False)
   - Consensus gain
2. End-to-end mode with a 4-member chat conversation, predicting or simulating
   emotion + expression intensity, constructing preference records, and computing
   decision, compromise plan, and consensus level.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.group_decision.conflict.schemas import EmotionSignal, PreferenceRecord
from app.group_decision.decision.baselines import METHODS
from app.group_decision.decision.consensus import (
    compute_consensus,
    decide_with_consensus,
    to_consensus_decision,
)

logger = logging.getLogger(__name__)

DEMO_GROUPS_PATH = ROOT_DIR / "data" / "group_decision" / "processed" / "decision_demo_groups.json"
ROBERTA_MODEL_DIR = ROOT_DIR / "models" / "roberta_emotion"
ROBERTA_THRESHOLDS_PATH = ROBERTA_MODEL_DIR / "thresholds.json"


def run_consensus_table(groups_path: Path | str = DEMO_GROUPS_PATH) -> None:
    """Print comparative consensus table for demo groups across decision methods."""
    path = Path(groups_path)
    if not path.exists():
        print(f"Error: Demo groups file not found at {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        groups = json.load(f)

    print("\n" + "=" * 132)
    print("STEP 10e: CONSENSUS LEVEL & FAIRNESS METRICS ACROSS METHODS")
    print("=" * 132)
    header_fmt = "{:<22} | {:<16} | {:<24} | {:<7} | {:<7} | {:<7} | {:<6} | {:<7} | {:<6}"
    row_fmt    = "{:<22} | {:<16} | {:<24} | {:<7.2f} | {:<7.2f} | {:<7.2f} | {:<6} | {:<7} | {:<+6.2f}"

    print(header_fmt.format(
        "Group ID", "Method", "Winner / Plan", "MeanAcc", "MinAcc", "Level", "Label", "Reached", "Gain"
    ))
    print("-" * 132)

    eval_methods = ["majority", "preference_only", "weighted", "weighted_minority"]

    for g in groups:
        gid = g.get("group_id", "GROUP")
        category = g.get("category", "Destination")
        records = g.get("records", [])

        for idx, method in enumerate(eval_methods):
            res, cons = decide_with_consensus(records, method=method, config={"category": category})
            cat_cons = cons.categories.get(category)
            if not cat_cons:
                continue

            plan_str = ", ".join(cat_cons.plan_items) if cat_cons.plan_items else str(cat_cons.primary_option)
            if len(plan_str) > 24:
                plan_str = plan_str[:21] + "..."

            display_gid = gid if idx == 0 else ""
            print(row_fmt.format(
                display_gid,
                method,
                plan_str,
                cat_cons.mean_acceptance,
                cat_cons.min_acceptance,
                cat_cons.consensus_level,
                cat_cons.level_label,
                str(cat_cons.consensus_reached),
                cat_cons.consensus_gain,
            ))
        print("-" * 132)


def run_end_to_end_chat_demo(chat_input: list[dict[str, Any]] | None = None) -> None:
    """Run end-to-end consensus workflow on a 4-member chat conversation."""
    print("\n" + "=" * 100)
    print("STEP 10e: END-TO-END CHAT -> EMOTION -> DECISION -> COMPROMISE -> CONSENSUS")
    print("=" * 100)

    # 1. Default hand-typed 4-member group chat if none provided
    if chat_input is None:
        chat_messages = [
            {
                "member": "Alice",
                "message_id": "m1",
                "text": "I really LOVE Ella so much!! We absolutely HAVE to go to Ella for the mountains!!",
                "category": "Destination",
                "stance": "positive",
                "option": "ella",
            },
            {
                "member": "Bob",
                "message_id": "m2",
                "text": "Ella sounds wonderful, I'm very happy and excited to hike Little Adam's Peak!",
                "category": "Destination",
                "stance": "positive",
                "option": "ella",
            },
            {
                "member": "Charlie",
                "message_id": "m3",
                "text": "I strongly hate Ella, it's way too crowded and noisy! I refuse to go to Ella. Sigiriya is much better!!",
                "category": "Destination",
                "stance": "negative",
                "option": "ella",
                "alt_option": "sigiriya",
                "alt_stance": "positive",
            },
            {
                "member": "David",
                "message_id": "m4",
                "text": "I approve of Ella or Sigiriya, both work fine for me.",
                "category": "Destination",
                "stance": "positive",
                "option": "ella",
            },
        ]
    else:
        chat_messages = chat_input

    # 2. Check model availability
    roberta_available = ROBERTA_MODEL_DIR.exists() and ROBERTA_THRESHOLDS_PATH.exists()
    if roberta_available:
        print("[Model Status] Fine-tuned RoBERTa model found at models/roberta_emotion. Running live inference.")
        from app.group_decision.emotion.predict import EmotionPredictor
        from app.group_decision.intensity.estimator import estimate_intensity
        predictor = EmotionPredictor(
            model_dir=ROBERTA_MODEL_DIR,
            thresholds_path=ROBERTA_THRESHOLDS_PATH,
        )
    else:
        print("[Model Status] Fine-tuned RoBERTa model not found at models/roberta_emotion.")
        print("               Using precomputed demo emotion and intensity signals as instructed.")

    # Precomputed fallback signals for demo chat messages
    fallback_signals: dict[str, dict[str, Any]] = {
        "m1": {"dominant_emotion": "love", "intensity": 0.92, "valence_sign": 1},
        "m2": {"dominant_emotion": "joy", "intensity": 0.78, "valence_sign": 1},
        "m3": {"dominant_emotion": "anger", "intensity": 0.88, "valence_sign": -1},
        "m4": {"dominant_emotion": "approval", "intensity": 0.25, "valence_sign": 1},
    }

    # 3. Construct PreferenceRecord objects with emotion signals
    structured_records: list[PreferenceRecord] = []
    print("\n--- Extracted Chat Signals ---")

    for msg in chat_messages:
        mid = msg["message_id"]
        member = msg["member"]
        text = msg["text"]
        cat = msg["category"]
        opt = msg["option"]
        st = msg["stance"]

        if roberta_available:
            try:
                preds = predictor.predict_probabilities([text])[0]
                est = estimate_intensity(text, preds)
                signal = EmotionSignal(
                    intensity=round(est["intensity"], 2),
                    valence_sign=est["valence_sign"],
                    dominant_emotion=est["dominant_emotion"],
                )
            except Exception as e:
                logger.warning("Inference error: %s. Using demo signal fallback.", e)
                sig_data = fallback_signals.get(mid, {"dominant_emotion": "approval", "intensity": 0.5, "valence_sign": 1})
                signal = EmotionSignal.model_validate(sig_data)
        else:
            sig_data = fallback_signals.get(mid, {"dominant_emotion": "approval", "intensity": 0.5, "valence_sign": 1})
            signal = EmotionSignal.model_validate(sig_data)

        rec = PreferenceRecord(
            member=member,
            category=cat,
            stance=st,
            value={"name": opt},
            message_id=mid,
            emotion=signal,
        )
        structured_records.append(rec)
        print(f"[{member}] \"{text}\"")
        print(f"       -> Emotion: {signal.dominant_emotion.upper()} | Intensity: {signal.intensity:.2f} | Valence: {signal.valence_sign:+d}")

        # Add second preference if member specified alternative
        if "alt_option" in msg and "alt_stance" in msg:
            alt_rec = PreferenceRecord(
                member=member,
                category=cat,
                stance=msg["alt_stance"],
                value={"name": msg["alt_option"]},
                message_id=mid + "_alt",
                emotion=signal,
            )
            structured_records.append(alt_rec)

    # 4. Run Weighted + Minority Protection decision and compute consensus
    print("\n--- Running Weighted + Minority Protection Decision & Consensus ---")
    res, cons = decide_with_consensus(
        structured_records,
        method="weighted_minority",
        config={"category": "Destination"},
    )

    dest_cons = cons.categories["Destination"]
    print(f"\nWinning Base Option : {dest_cons.primary_option}")
    print(f"Compromise Plan     : {dest_cons.plan_items}")
    print(f"Member Acceptances  : {dest_cons.member_acceptance}")
    print(f"Mean Acceptance     : {dest_cons.mean_acceptance:.2f}")
    print(f"Min Acceptance      : {dest_cons.min_acceptance:.2f}")
    print(f"Consensus Level     : {dest_cons.consensus_level:.2f} ({dest_cons.level_label.upper()})")
    print(f"Consensus Reached   : {dest_cons.consensus_reached}")
    print(f"Consensus Gain      : {dest_cons.consensus_gain:+.2f} (from primary-only {dest_cons.consensus_primary_only:.2f})")
    print(f"Gini Coefficient    : {dest_cons.gini:.4f}")
    print(f"Satisfaction Gap    : {dest_cons.satisfaction_gap:.2f}")

    # 5. Coordinator API Payload Check
    coord_payload = to_consensus_decision(cons, res)
    print("\n--- Coordinator Output Payload ---")
    print(json.dumps(coord_payload, indent=2))
    print("=" * 100 + "\n")


def main() -> None:
    """Parse CLI options and execute consensus demonstrations."""
    parser = argparse.ArgumentParser(description="WANDARAYA Step 10e: Consensus & Fairness Metrics Demo")
    parser.add_argument("--end-to-end", action="store_true", help="Run end-to-end 4-member chat mode")
    parser.add_argument("--table", action="store_true", help="Run demo groups comparative table")
    args = parser.parse_args()

    # Default: run both table and end-to-end
    run_all = not args.end_to_end and not args.table
    if run_all or args.table:
        run_consensus_table()
    if run_all or args.end_to_end:
        run_end_to_end_chat_demo()


if __name__ == "__main__":
    main()
