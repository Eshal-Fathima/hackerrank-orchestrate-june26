"""
evaluation/main.py
Evaluates system output against sample_claims.csv ground truth.
Prints accuracy, per-class metrics, and common failure modes.

Usage:
    python code/evaluation/main.py
    python code/evaluation/main.py --sample dataset/sample_claims.csv --output output.csv
"""

import csv, sys, time, argparse
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))


VERDICT_COL    = "claim_status"
EXPECTED_COL   = "claim_status"   # same column name in sample_claims.csv
VALID_VERDICTS = {"supported", "contradicted", "not_enough_information"}


def load_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def evaluate(sample_path: str, output_path: str) -> dict:
    sample = load_csv(sample_path)
    output = load_csv(output_path)

    # Index output by user_id + image_paths (composite key since no claim_id)
    def key(row):
        return (row.get("user_id", "").strip(), row.get("image_paths", "").strip())

    output_index = {key(r): r for r in output}

    total    = 0
    correct  = 0
    missing  = 0
    failures = []

    confusion = defaultdict(Counter)  # confusion[expected][predicted] += 1
    flag_hits = Counter()

    for row in sample:
        k = key(row)
        expected = row.get(EXPECTED_COL, "").strip()
        if expected not in VALID_VERDICTS:
            continue

        total += 1
        if k not in output_index:
            missing += 1
            failures.append({
                "user_id": row.get("user_id"),
                "expected": expected,
                "predicted": "MISSING",
                "image_paths": row.get("image_paths", ""),
            })
            confusion[expected]["MISSING"] += 1
            continue

        predicted = output_index[k].get(VERDICT_COL, "").strip()
        confusion[expected][predicted] += 1

        if predicted == expected:
            correct += 1
        else:
            failures.append({
                "user_id": row.get("user_id"),
                "expected": expected,
                "predicted": predicted,
                "claim": row.get("user_claim", "")[:80],
                "flags": output_index[k].get("risk_flags", ""),
            })

        # Flag accuracy
        expected_flags = set(row.get("risk_flags", "none").replace("none","").split(";"))
        predicted_flags = set(output_index[k].get("risk_flags", "none").replace("none","").split(";"))
        expected_flags.discard("")
        predicted_flags.discard("")
        for f in expected_flags & predicted_flags:
            flag_hits[f] += 1

    accuracy = correct / total if total else 0

    return {
        "total": total,
        "correct": correct,
        "missing": missing,
        "accuracy": accuracy,
        "confusion": dict(confusion),
        "failures": failures,
        "flag_hits": dict(flag_hits),
    }


def print_report(metrics: dict, output_path: str):
    print("\n" + "="*60)
    print("  EVALUATION REPORT")
    print("="*60)
    print(f"  Total samples:  {metrics['total']}")
    print(f"  Correct:        {metrics['correct']}")
    print(f"  Missing rows:   {metrics['missing']}")
    print(f"  Accuracy:       {metrics['accuracy']*100:.1f}%")
    print()

    print("  Confusion matrix (expected → predicted):")
    labels = ["supported", "contradicted", "not_enough_information"]
    header = f"{'':30s}" + "".join(f"{l[:12]:>14s}" for l in labels)
    print("  " + header)
    for exp in labels:
        row_counts = metrics["confusion"].get(exp, {})
        row_str = f"  {exp:30s}"
        for pred in labels:
            row_str += f"{row_counts.get(pred, 0):>14d}"
        print(row_str)

    print()
    print(f"  Failures ({len(metrics['failures'])}):")
    for f in metrics["failures"][:10]:
        print(f"    [{f['user_id']}] expected={f['expected']:30s} predicted={f['predicted']}")
        if "claim" in f:
            print(f"      claim: {f['claim']}...")
    if len(metrics["failures"]) > 10:
        print(f"    ... and {len(metrics['failures'])-10} more")

    print()
    print(f"  Flag matches: {metrics['flag_hits']}")
    print("="*60)

    # Write markdown report
    report_path = Path(__file__).parent / "evaluation_report.md"
    with open(report_path, "w") as f:
        f.write(f"# Evaluation Report\n\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## Summary\n\n")
        f.write(f"| Metric | Value |\n|--------|-------|\n")
        f.write(f"| Total samples | {metrics['total']} |\n")
        f.write(f"| Correct | {metrics['correct']} |\n")
        f.write(f"| Accuracy | {metrics['accuracy']*100:.1f}% |\n\n")
        f.write(f"## Failures\n\n")
        for fail in metrics["failures"]:
            f.write(f"- `{fail['user_id']}`: expected `{fail['expected']}`, got `{fail['predicted']}`\n")
    print(f"\n  Report written to {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", default="dataset/sample_claims.csv")
    parser.add_argument("--output", default="output.csv")
    args = parser.parse_args()

    metrics = evaluate(args.sample, args.output)
    print_report(metrics, args.output)