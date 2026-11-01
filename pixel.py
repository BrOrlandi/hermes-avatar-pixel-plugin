"""Pure image and prompt helpers for avatar-pixel (no Hermes imports, so they test standalone)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PIL import Image

SIDE = 512

STYLE_PROMPT = (
    "Pixel art game sprite in exactly the same style as the first {n} reference images (they are style "
    "examples only, do not copy their subjects): chunky visible pixels (about 48 pixels tall overall), "
    "crisp dark 1-pixel outline, flat colors with 2-3 shading tones per color, no anti-aliasing, no "
    "gradients, no text, no letters, no drop shadow, cute chibi proportions, three-quarter view, "
    "centered, filling about 80% of the frame. Solid flat magenta background (#FF00FF) everywhere "
    "outside the sprite, including any gaps and holes inside it; do not use magenta in the sprite. "
    "Nothing else in the scene. {extra}Subject: "
)
REFERENCES_HINT = ("The remaining reference images show what the subject looks like: follow their shapes "
                   "and colors, redrawn as a pixel art sprite. ")

# Prompts the Hermes Desktop sends from Edit profile -> Generate (profile-ops bundle).
_DESKTOP_DEFAULT = re.compile(
    r'^Cute minimal robot avatar for an AI agent named "(?P<who>.*)"\. Friendly simple mascot face', re.S)
_DESKTOP_TYPED = re.compile(
    r"^(?P<text>.*)\. Avatar for an AI agent: centered, bold flat vector style", re.S)


def parse_avatar_prompt(prompt: str) -> Optional[dict]:
    """Recognize a Desktop avatar prompt. Returns {"title", "description"} for the default button,
    {"text"} when the user typed something in the box, or None for any other image request."""
    m = _DESKTOP_DEFAULT.match(prompt.strip())
    if m:
        title, _, description = m.group("who").partition(" — ")
        return {"title": title.strip(), "description": description.strip()}
    m = _DESKTOP_TYPED.match(prompt.strip())
    if m and m.group("text").strip():
        return {"text": m.group("text").strip()}
    return None


def subject_for_unknown(title: str, description: str) -> str:
    """Subject for an agent that has no catalog entry: let the model pick one symbol for the role."""
    role = f'an AI assistant called "{title}"' + (f" whose job is: {description}" if description else "")
    return (f"one single concrete object or small character that clearly symbolizes {role}. "
            "Pick the most recognizable symbol for that job; no text, no screens with writing.")


def build_prompt(subject: str, n_style: int, has_references: bool) -> str:
    return STYLE_PROMPT.format(n=n_style, extra=REFERENCES_HINT if has_references else "") + subject


def _is_magenta(r: int, g: int, b: int) -> bool:
    return r > 170 and b > 170 and g < 100 and abs(r - b) < 80


def remove_background(img: Image.Image, holes: Optional[list] = None, tolerance: int = 40) -> Image.Image:
    """Make the background transparent. Magenta background (what the prompt asks for): every magenta
    pixel goes, holes included. White background (the model sometimes ignores the request): flood
    fill from the borders and from the extra seed points in ``holes`` ([x, y]), so white inside the
    sprite survives."""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    if _is_magenta(*px[0, 0][:3]) and _is_magenta(*px[w - 1, h - 1][:3]):
        for y in range(h):
            for x in range(w):
                if _is_magenta(*px[x, y][:3]):
                    px[x, y] = (0, 0, 0, 0)
        return img
    seen = bytearray(w * h)
    stack = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    stack += [tuple(p) for p in (holes or [])]
    while stack:
        x, y = stack.pop()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        r, g, b, a = px[x, y]
        if a and min(r, g, b) < 255 - tolerance:
            continue
        px[x, y] = (0, 0, 0, 0)
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                stack.append((nx, ny))
    return img


def fit_square(sprite: Image.Image, margin: float = 0.02) -> Image.Image:
    """Crop to the sprite and scale it up (nearest neighbour) to fill a SIDE x SIDE square."""
    bbox = sprite.getbbox()
    if not bbox:
        raise ValueError("the generated image is empty after removing the background")
    s = sprite.crop(bbox)
    side = round(max(s.size) * (1 + 2 * margin))
    frame = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    frame.alpha_composite(s, ((side - s.width) // 2, (side - s.height) // 2))
    return frame.resize((SIDE, SIDE), Image.NEAREST)


def find_catalog_entry(catalog: dict, title: str) -> Optional[dict]:
    """Catalog entry whose key or name matches the Desktop title (case-insensitive)."""
    t = title.strip().casefold()
    for key, entry in catalog.items():
        if not isinstance(entry, dict):
            continue
        names = {key, entry.get("name", ""), entry.get("nome", ""), entry.get("title", "")}
        if t in {str(n).strip().casefold() for n in names if n}:
            return entry
    return None


def entry_field(entry: dict, *keys: str):
    """First present field, so the catalog can use English keys or the Portuguese ones."""
    for k in keys:
        if entry.get(k):
            return entry[k]
    return None


def resolve_paths(base: Path, values) -> list[Path]:
    return [(base / v) for v in (values or [])]
