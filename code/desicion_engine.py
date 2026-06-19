"""
decision_engine.py
Pure rule-based engine. No AI calls here.
Takes outputs from all other modules and produces the final verdict + all output fields.
"""


# Mapping loose synonyms to canonical issue types
ISSUE_SYNONYMS = {
    "cracked": "crack",
    "cracking": "crack",
    "broken": "broken_part",
    "broke": "broken_part",
    "missing_part": "broken_part",
    "dented": "dent",
    "scratched": "scratch",
    "stained": "stain",
    "wet": "water_damage",
    "liquid": "liquid_damage",
    "crushed": "crushed_packaging",
    "torn": "torn_packaging",
    "missing": "missing_contents",
    "hail": "hail_damage",
}

PART_SYNONYMS = {
    "bumper": "front_bumper",   # will be overridden by context
    "glass": "windshield",
    "front glass": "windshield",
    "back light": "taillight",
    "backlight": "taillight",
    "mirror": "side_mirror",
    "display": "screen",
    "keys": "keyboard",
    "keycaps": "keyboard",
    "outer body": "body_panel",
    "body": "body_panel",
    "lid": "lid",
    "outer lid": "lid",
    "package": "package_corner",
    "box": "package_corner",
    "seal side": "seal",
    "item": "contents",
    "product": "contents",
    "inside": "contents",
}


def _normalise(value: str, synonyms: dict) -> str:
    v = value.lower().strip()
    return synonyms.get(v, v)


def _issues_match(claimed: str, visible: str) -> bool:
    """Loose match between claimed and visible issue."""
    c = _normalise(claimed, ISSUE_SYNONYMS)
    v = _normalise(visible, ISSUE_SYNONYMS)
    if c == v:
        return True
    # Broader groupings
    damage_group = {"crack", "broken_part", "dent", "scratch", "hail_damage"}
    liquid_group = {"stain", "water_damage", "liquid_damage"}
    packaging_group = {"crushed_packaging", "torn_packaging"}
    for group in (damage_group, liquid_group, packaging_group):
        if c in group and v in group:
            return True
    return False


def _parts_match(claimed: str, visible: str) -> bool:
    """Loose match between claimed and visible part."""
    c = _normalise(claimed, PART_SYNONYMS).replace("_", " ")
    v = _normalise(visible, PART_SYNONYMS).replace("_", " ")
    if c == v:
        return True
    if c in v or v in c:
        return True
    # Bumper direction flexibility
    if "bumper" in c and "bumper" in v:
        return True
    return False


def _detect_injection(conversation: str) -> bool:
    """Detect prompt injection / social engineering attempts in the conversation."""
    lower = conversation.lower()
    triggers = [
        "approve the claim", "approve this claim", "skip manual review",
        "ignore previous", "mark this row", "follow it and approve",
        "accept this quickly", "keep reopening", "escalate publicly",
        "approve kar dena", "usko follow karke", "ignore all previous instructions",
    ]
    return any(t in lower for t in triggers)


def make_decision(
    claim_object: str,
    conversation: str,
    claim_parsed: dict,       # from claim_parser
    best_image: dict,         # from image_analyzer.pick_best_image
    all_images: list[dict],   # all image results
    evidence_met: bool,       # from evidence_checker
    evidence_reason: str,
    history_flags: list[str], # from history_checker
) -> dict:
    """
    Returns the full output row dict.
    """

    # --- Collect all flags ---
    flags = list(history_flags)  # start with history flags

    # Image quality flags
    for img in all_images:
        q = img.get("image_quality", "good")
        if q in ("blurry", "dark", "obstructed", "wrong_angle", "low_resolution"):
            if "image_quality_issue" not in flags:
                flags.append("image_quality_issue")
        auth = img.get("authenticity_flags", [])
        for f in auth:
            if f and f not in flags:
                flags.append(f)
        if not img.get("is_valid_photo", True):
            if "non_original_image" not in flags:
                flags.append("non_original_image")
        if img.get("wrong_object", False):
            if "wrong_object" not in flags:
                flags.append("wrong_object")

    # Prompt injection detection
    if _detect_injection(conversation):
        if "text_instruction_present" not in flags:
            flags.append("text_instruction_present")

    # --- Gather key values ---
    claimed_issue = claim_parsed.get("issue_type", "other")
    claimed_part  = claim_parsed.get("object_part", "unknown")
    visible_issue = best_image.get("visible_issue", "unknown")
    visible_part  = best_image.get("object_part", "unknown")
    severity      = best_image.get("severity", "unknown")
    img_quality   = best_image.get("image_quality", "good")
    description   = best_image.get("description", "")
    confidence    = float(best_image.get("confidence", 0.5))

    # Supporting image IDs
    supporting_ids = []
    for img in all_images:
        p = img.get("image_path", "")
        if p:
            # Extract just the filename stem, e.g. "img_1"
            from pathlib import Path
            stem = Path(p).stem
            # Only include images that are relevant (not wrong object, not missing)
            if not img.get("wrong_object", False) and img.get("image_quality") != "missing":
                supporting_ids.append(stem)

    valid_image = all(img.get("is_valid_photo", True) for img in all_images)

    # --- Determine verdict ---
    verdict = "not_enough_information"
    justification = ""

    # Rule 1: evidence not met → not_enough_information
    if not evidence_met:
        verdict = "not_enough_information"
        justification = f"Evidence standard not met. {evidence_reason}"
        if "wrong_object" not in flags and "damage_not_visible" not in flags:
            flags.append("damage_not_visible")

    # Rule 2: image shows nothing (visible_issue is none/unknown) → not_enough_information
    elif visible_issue in ("none", "unknown", "") and img_quality in ("blurry", "dark", "obstructed", "wrong_angle"):
        verdict = "not_enough_information"
        justification = f"Image quality is {img_quality} and no damage is visible to evaluate the claim."
        if "image_quality_issue" not in flags:
            flags.append("image_quality_issue")

    # Rule 3: wrong object in all images → not_enough_information
    elif all(img.get("wrong_object", False) for img in all_images if all_images):
        verdict = "not_enough_information"
        justification = "All submitted images appear to show a different object than claimed."
        if "wrong_object" not in flags:
            flags.append("wrong_object")

    # Rule 4: issue matches AND part matches → supported
    elif _issues_match(claimed_issue, visible_issue) and _parts_match(claimed_part, visible_part):
        verdict = "supported"
        justification = (
            f"The image shows {visible_issue} on the {visible_part}, "
            f"which matches the claimed {claimed_issue} on the {claimed_part}. {description}"
        ).strip()

    # Rule 5: part IS visible but damage does NOT match → contradicted
    elif _parts_match(claimed_part, visible_part) and visible_issue not in ("unknown", "none", ""):
        verdict = "contradicted"
        justification = (
            f"The {visible_part} is visible but shows {visible_issue} rather than the claimed {claimed_issue}. "
            f"{description}"
        ).strip()
        if "claim_mismatch" not in flags:
            flags.append("claim_mismatch")

    # Rule 6: part visible but no damage → contradicted
    elif _parts_match(claimed_part, visible_part) and visible_issue in ("none",):
        verdict = "contradicted"
        justification = f"The {visible_part} is clearly visible but no {claimed_issue} is present. {description}"
        if "claim_mismatch" not in flags:
            flags.append("claim_mismatch")

    # Rule 7: can't tell → not_enough_information
    else:
        verdict = "not_enough_information"
        justification = (
            f"The submitted image does not clearly show the claimed {claimed_part} "
            f"or the visible content does not confirm the {claimed_issue} claim. {description}"
        ).strip()
        if "damage_not_visible" not in flags:
            flags.append("damage_not_visible")

    # Add manual_review_required if there are risk flags
    risky_flags = {"user_history_risk", "text_instruction_present", "non_original_image",
                   "wrong_object", "claim_mismatch", "authenticity_concern"}
    if any(f in flags for f in risky_flags):
        if "manual_review_required" not in flags:
            flags.append("manual_review_required")

    # Clean flags — deduplicate
    seen = set()
    clean_flags = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            clean_flags.append(f)

    return {
        "evidence_standard_met": evidence_met,
        "evidence_standard_met_reason": evidence_reason,
        "risk_flags": ";".join(clean_flags) if clean_flags else "none",
        "issue_type": visible_issue if visible_issue not in ("unknown", "") else claimed_issue,
        "object_part": visible_part if visible_part not in ("unknown", "") else claimed_part,
        "claim_status": verdict,
        "claim_status_justification": justification,
        "supporting_image_ids": ";".join(supporting_ids) if supporting_ids else "none",
        "valid_image": str(valid_image).lower(),
        "severity": severity,
    }