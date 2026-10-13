"""Storyboard: the same character or object from different camera angles.

Ported from the standalone AI Image Studio. Each view is one edit of the
reference picture on a Gemini image model (they keep the identity best);
labels live in the frontend catalogs, the instructions stay in English
because models follow camera terms in English most reliably.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StoryboardView:
    id: str
    group: str  # "portrait" | "full_body" | "special"
    instruction: str


VIEWS: tuple[StoryboardView, ...] = (
    StoryboardView("front", "portrait", "front view, looking straight at the camera"),
    StoryboardView("three_quarter_left", "portrait", "three-quarter view from the left (about 45 degrees)"),
    StoryboardView("three_quarter_right", "portrait", "three-quarter view from the right (about 45 degrees)"),
    StoryboardView("profile_left", "portrait", "left side profile view (90 degrees)"),
    StoryboardView("profile_right", "portrait", "right side profile view (90 degrees)"),
    StoryboardView("back", "portrait", "back view, seen from behind"),
    StoryboardView("full_front", "full_body", "full body shot, front view, whole figure visible head to toe"),
    StoryboardView("full_side", "full_body", "full body shot, side view, whole figure visible head to toe"),
    StoryboardView("full_back", "full_body", "full body shot, back view, whole figure visible head to toe"),
    StoryboardView("top", "special", "top-down view, seen from above"),
    StoryboardView("bottom", "special", "low-angle view, seen from below"),
    StoryboardView("closeup", "special", "extreme close-up, detailed shot of the main subject"),
)
VIEWS_BY_ID = {view.id: view for view in VIEWS}


def view_prompt(view: StoryboardView, details: str = "") -> str:
    prompt = (
        "Using the SAME character/object from the reference image, generate a new image "
        f"showing it in this view: {view.instruction}. "
        "CRITICAL: keep the exact same identity, face, hairstyle, clothing, colors, proportions "
        "and style as the reference. Only the camera angle / point of view changes. "
        "Use a clean, neutral background. High detail, sharp, consistent lighting."
    )
    details = " ".join(details.split())
    return f"{prompt} Additional details: {details}" if details else prompt


def public_views() -> list[dict]:
    return [{"id": view.id, "group": view.group} for view in VIEWS]
