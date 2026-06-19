# Damage Claim Verification System

Multi-modal evidence review pipeline for verifying damage claims using images and conversation context.

## Architecture

```
claims.csv
    │
    ├─► claim_parser.py      (LLM) → extracts issue_type + object_part from conversation
    ├─► image_analyzer.py    (Gemini Vision) → analyzes each image, returns structured JSON
    ├─► evidence_checker.py  (rules) → checks minimum evidence requirements
    ├─► history_checker.py   (rules) → reads user_history.csv, returns risk flags
    └─► decision_engine.py   (rules) → combines all inputs → final verdict
                                              │
                                         output.csv
```

## Model Used

- **Gemini 2.5 Flash** (via `google-generativeai`) for both text (claim parsing) and vision (image analysis)

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

## Run

```bash
# Process all claims → output.csv
python code/main.py

# Custom paths
python code/main.py --input dataset/claims.csv --output output.csv --dataset dataset/

# Evaluate against sample_claims.csv
python code/evaluation/main.py
```

## Output Schema

| Column | Type | Description |
|--------|------|-------------|
| user_id | str | User identifier |
| image_paths | str | Semicolon-separated image paths |
| user_claim | str | Original conversation |
| claim_object | str | car / laptop / package |
| evidence_standard_met | bool | Whether images meet minimum evidence rules |
| evidence_standard_met_reason | str | Explanation |
| risk_flags | str | Semicolon-separated flags (none if clean) |
| issue_type | str | Damage type visible in image |
| object_part | str | Part of object affected |
| claim_status | str | supported / contradicted / not_enough_information |
| claim_status_justification | str | One-sentence explanation grounded in image |
| supporting_image_ids | str | Image filenames supporting the verdict |
| valid_image | bool | Whether images appear to be original photos |
| severity | str | low / medium / high / critical / unknown |

## Key Design Decisions

- **Images are the primary source of truth.** User history can add risk flags but never overrides the visual verdict.
- **Prompt injection resistance.** Conversations containing instructions like "approve this claim" or "ignore previous instructions" are flagged and ignored.
- **Evidence-first.** If the relevant part is not visible in any image, the verdict is `not_enough_information` regardless of anything else.
- **Pure rule-based decision engine.** No AI in the final verdict step — deterministic and auditable.