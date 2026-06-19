"""
evidence_checker.py
Checks whether the submitted image evidence meets minimum requirements
based on evidence_requirements.csv.
Returns: (met: bool, reason: str)
"""

from pathlib import Path


# Hard-coded rules derived directly from evidence_requirements.csv
# This avoids loading CSV at runtime and makes logic explicit.

def check_evidence(
    claim_object: str,        # car | laptop | package
    claimed_part: str,        # e.g. screen, rear_bumper
    claimed_issue: str,       # e.g. crack, dent
    image_results: list[dict], # list of analyze_image() outputs
) -> tuple[bool, str]:
    """
    Returns (evidence_standard_met: bool, reason: str)
    """
    if not image_results:
        return False, "No images were submitted or could be analyzed."

    # --- Check for completely unreadable images ---
    usable = [r for r in image_results if r.get("image_quality") not in ("missing",)]
    if not usable:
        return False, "All submitted images are missing or unreadable."

    # --- REQ_REVIEW_TRUST: images must be relevant ---
    all_wrong_object = all(r.get("wrong_object", False) for r in image_results)
    if all_wrong_object:
        return False, "All images show a different object than claimed."

    # At least one image must be usable for the claim
    # REQ_GENERAL_MULTI_IMAGE: at least one relevant image should show claimed object
    relevant = [r for r in image_results
                if not r.get("wrong_object", False)
                and r.get("image_quality") not in ("missing",)
                and r.get("object_type", "unknown") in (claim_object, "unknown")]

    if not relevant:
        return False, "No submitted image shows the claimed object type."

    # Find best usable image
    good_quality = [r for r in relevant
                    if r.get("image_quality") in ("good", "low_resolution")]

    part_lower = claimed_part.lower()
    issue_lower = claimed_issue.lower()

    # --- Object-specific rules ---
    if claim_object == "car":
        glass_light_parts = {"windshield", "headlight", "taillight", "side_mirror", "light"}
        body_parts = {"front_bumper", "rear_bumper", "door", "hood", "body_panel", "bumper"}

        if any(p in part_lower for p in glass_light_parts):
            # REQ_CAR_GLASS_LIGHT_MIRROR
            part_visible = any(
                part_lower in str(r.get("object_part", "")).lower()
                for r in relevant
            )
            if not part_visible:
                return False, f"The claimed {claimed_part} is not clearly visible in any submitted image."
            return True, f"The {claimed_part} is visible and can be inspected for {claimed_issue}."

        elif any(p in part_lower for p in body_parts):
            # REQ_CAR_BODY_PANEL
            if not good_quality:
                return False, "Images are too blurry or obstructed to assess surface damage."
            part_visible = any(
                part_lower.replace("_", " ") in str(r.get("object_part", "")).lower()
                or part_lower in str(r.get("object_part", "")).lower()
                for r in relevant
            )
            if not part_visible:
                return False, f"The claimed {claimed_part} is not clearly visible for damage assessment."
            return True, f"The {claimed_part} is visible at an angle where {claimed_issue} can be assessed."

        else:
            # General car part
            if not relevant:
                return False, "No usable car image submitted."
            return True, "The image provides sufficient context for car damage review."

    elif claim_object == "laptop":
        screen_keyboard_parts = {"screen", "keyboard", "trackpad", "display"}
        body_parts = {"hinge", "lid", "corner", "body", "body_panel", "port", "base"}

        if any(p in part_lower for p in screen_keyboard_parts):
            # REQ_LAPTOP_SCREEN_KEYBOARD_TRACKPAD
            part_visible = any(
                part_lower in str(r.get("object_part", "")).lower()
                for r in relevant
            )
            if not part_visible and not good_quality:
                return False, f"The {claimed_part} is not clearly visible for inspection."
            return True, f"The {claimed_part} area is visible and can be inspected for {claimed_issue}."

        elif any(p in part_lower for p in body_parts):
            # REQ_LAPTOP_BODY_HINGE_PORT
            if not relevant:
                return False, "No usable laptop image submitted."
            return True, f"The laptop {claimed_part} is visible with enough context."

        else:
            if not relevant:
                return False, "No usable laptop image submitted."
            return True, "The image provides sufficient context for laptop damage review."

    elif claim_object == "package":
        exterior_parts = {"package_corner", "corner", "seal", "flap", "package_side", "box"}
        label_parts = {"label"}
        contents_parts = {"contents", "item", "product"}

        if any(p in part_lower for p in contents_parts):
            # REQ_PACKAGE_CONTENTS — needs to show opened package
            part_visible = any(
                str(r.get("object_part", "")).lower() in ("contents", "item", "product", "interior")
                for r in relevant
            )
            if not part_visible:
                return False, "The opened package interior is not clearly visible to verify missing contents."
            return True, "The opened package and contents area are visible."

        elif any(p in part_lower for p in label_parts):
            # REQ_PACKAGE_LABEL_OR_STAIN
            return True, "The package surface/label area is visible for inspection."

        else:
            # REQ_PACKAGE_EXTERIOR
            if not relevant:
                return False, "No usable package image submitted."
            return True, "The package exterior is visible for damage inspection."

    # Fallback
    return True, "Submitted images provide sufficient context for review."