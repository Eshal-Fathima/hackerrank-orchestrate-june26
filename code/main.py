"""
main.py
Entry point for the damage claim verification pipeline.
Reads: dataset/claims.csv + images + user_history.csv + evidence_requirements.csv
Writes: output.csv

Usage:
    python code/main.py
    python code/main.py --input dataset/claims.csv --output output.csv --dataset dataset/
"""

import os, sys, csv, json, time, argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add code/ to path so imports work from repo root
sys.path.insert(0, str(Path(__file__).parent))

from claim_parser import parse_claim
from image_analyzer import analyze_all_images, pick_best_image
from evidence_checker import check_evidence
from history_checker import get_history_flags
from decision_engine import make_decision

# ── Logging ────────────────────────────────────────────────────────────────
LOG_PATH = Path.home() / "hackerrank_orchestrate" / "log.txt"

def log(msg: str):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


# ── Main Pipeline ───────────────────────────────────────────────────────────
OUTPUT_COLUMNS = [
    "user_id", "image_paths", "user_claim", "claim_object",
    "evidence_standard_met", "evidence_standard_met_reason",
    "risk_flags", "issue_type", "object_part",
    "claim_status", "claim_status_justification",
    "supporting_image_ids", "valid_image", "severity",
]


def process_claim(row: dict, dataset_dir: Path, history_csv: str) -> dict:
    """Process a single claim row and return the output dict."""
    user_id      = row["user_id"]
    claim_object = row["claim_object"]
    conversation = row["user_claim"]
    image_paths_raw = row["image_paths"]

    print(f"\n  → {user_id} | {claim_object} | {image_paths_raw.split(';')[0]}")

    # Resolve image paths relative to dataset dir
    image_paths = [
        str(dataset_dir / p.strip())
        for p in image_paths_raw.split(";")
        if p.strip()
    ]

    # Step 1: Parse the claim conversation
    print("    [1] Parsing claim...")
    claim_parsed = parse_claim(conversation)
    print(f"        issue={claim_parsed['issue_type']} part={claim_parsed['object_part']}")

    # Step 2: Analyze all images
    print(f"    [2] Analyzing {len(image_paths)} image(s)...")
    image_results = analyze_all_images(image_paths)
    best_image = pick_best_image(image_results, claim_parsed["object_part"])

    # Step 3: Check evidence requirements
    print("    [3] Checking evidence...")
    evidence_met, evidence_reason = check_evidence(
        claim_object=claim_object,
        claimed_part=claim_parsed["object_part"],
        claimed_issue=claim_parsed["issue_type"],
        image_results=image_results,
    )

    # Step 4: Get user history flags
    print("    [4] Checking user history...")
    history_flags = get_history_flags(user_id, history_csv)

    # Step 5: Make decision
    print("    [5] Making decision...")
    decision = make_decision(
        claim_object=claim_object,
        conversation=conversation,
        claim_parsed=claim_parsed,
        best_image=best_image,
        all_images=image_results,
        evidence_met=evidence_met,
        evidence_reason=evidence_reason,
        history_flags=history_flags,
    )

    print(f"        ✓ status={decision['claim_status']} | flags={decision['risk_flags']}")

    # Build full output row (preserve input columns + add output columns)
    output_row = {
        "user_id": user_id,
        "image_paths": image_paths_raw,
        "user_claim": conversation,
        "claim_object": claim_object,
        **decision,
    }
    return output_row


def run(input_csv: str, output_csv: str, dataset_dir: str):
    dataset_path = Path(dataset_dir)
    history_csv  = str(dataset_path / "user_history.csv")

    # Read input
    with open(input_csv, newline="", encoding="utf-8") as f:
        claims = list(csv.DictReader(f))

    print(f"\n{'='*60}")
    print(f"Processing {len(claims)} claims from {input_csv}")
    print(f"Dataset dir: {dataset_path}")
    print(f"Output: {output_csv}")
    print(f"{'='*60}")

    log(f"\n## SESSION RUN — {time.strftime('%Y-%m-%dT%H:%M:%S')}\nInput: {input_csv}\nClaims: {len(claims)}")

    results = []
    errors  = []

    for i, row in enumerate(claims, 1):
        print(f"\n[{i}/{len(claims)}]", end="")
        try:
            result = process_claim(row, dataset_path, history_csv)
            results.append(result)
            log(f"  OK  [{i}] {row['user_id']} → {result['claim_status']}")
        except Exception as e:
            print(f"\n  !! ERROR on row {i}: {e}")
            errors.append((i, row.get("user_id", "?"), str(e)))
            log(f"  ERR [{i}] {row.get('user_id','?')} → {e}")
            # Write a fallback row so output.csv always has all rows
            results.append({
                "user_id": row.get("user_id", ""),
                "image_paths": row.get("image_paths", ""),
                "user_claim": row.get("user_claim", ""),
                "claim_object": row.get("claim_object", ""),
                "evidence_standard_met": False,
                "evidence_standard_met_reason": f"Processing error: {e}",
                "risk_flags": "processing_error",
                "issue_type": "unknown",
                "object_part": "unknown",
                "claim_status": "not_enough_information",
                "claim_status_justification": f"System error during processing: {e}",
                "supporting_image_ids": "none",
                "valid_image": "false",
                "severity": "unknown",
            })

    # Write output CSV
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in results:
            writer.writerow({k: row.get(k, "") for k in OUTPUT_COLUMNS})

    print(f"\n\n{'='*60}")
    print(f"✓ Done. {len(results)} rows written to {output_csv}")
    if errors:
        print(f"  ⚠ {len(errors)} errors: {errors}")

    verdicts = [r["claim_status"] for r in results]
    from collections import Counter
    print(f"  Verdicts: {dict(Counter(verdicts))}")
    log(f"  Done. Verdicts: {dict(Counter(verdicts))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",   default="dataset/claims.csv")
    parser.add_argument("--output",  default="output.csv")
    parser.add_argument("--dataset", default="dataset")
    args = parser.parse_args()
    run(args.input, args.output, args.dataset)