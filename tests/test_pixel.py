import sys
from pathlib import Path

import pytest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pixel  # noqa: E402

DEFAULT = ('Cute minimal robot avatar for an AI agent named "Finance Bot — Tracks my bills". '
           "Friendly simple mascot face, bold flat vector style, solid color background, centered, no text.")
TYPED = "a red sports car. Avatar for an AI agent: centered, bold flat vector style, solid color background, no text."


def test_parse_default_button():
    assert pixel.parse_avatar_prompt(DEFAULT) == {"title": "Finance Bot", "description": "Tracks my bills"}


def test_parse_typed_text():
    assert pixel.parse_avatar_prompt(TYPED) == {"text": "a red sports car"}


def test_other_prompts_pass_through():
    assert pixel.parse_avatar_prompt("A sunset over the sea") is None
    assert pixel.parse_avatar_prompt("Group chat icon for an AI agent team called \"x\".") is None


def test_catalog_match_by_key_or_name():
    cat = {"financas": {"nome": "Finanças", "assunto": "coin"}, "dev": {"name": "Developer Bot"}}
    assert pixel.find_catalog_entry(cat, "finanças")["assunto"] == "coin"
    assert pixel.find_catalog_entry(cat, "developer bot") is cat["dev"]
    assert pixel.find_catalog_entry(cat, "dev") is cat["dev"]
    assert pixel.find_catalog_entry(cat, "nobody") is None


def test_magenta_background_removed_and_fills_square():
    img = Image.new("RGB", (100, 100), (255, 0, 255))
    for x in range(40, 60):
        for y in range(30, 70):
            img.putpixel((x, y), (20, 120, 40))
    out = pixel.fit_square(pixel.remove_background(img))
    assert out.size == (pixel.SIDE, pixel.SIDE)
    assert out.getpixel((0, 0))[3] == 0
    assert out.getpixel((pixel.SIDE // 2, pixel.SIDE // 2))[:3] == (20, 120, 40)
    bbox = out.getbbox()
    assert bbox[3] - bbox[1] > pixel.SIDE * 0.9  # tall side fills the square


def test_white_background_keeps_inner_white():
    img = Image.new("RGB", (60, 60), (255, 255, 255))
    for x in range(10, 50):
        for y in range(10, 50):
            border = x in (10, 49) or y in (10, 49)
            img.putpixel((x, y), (0, 0, 0) if border else (255, 255, 255))
    out = pixel.remove_background(img)
    assert out.getpixel((0, 0))[3] == 0
    assert out.getpixel((30, 30))[3] == 255


def test_prompt_mentions_references_only_when_present():
    assert pixel.REFERENCES_HINT in pixel.build_prompt("a cat", 3, True)
    assert pixel.REFERENCES_HINT not in pixel.build_prompt("a cat", 3, False)


def test_modes():
    assert pixel.split_mode("robot, holding keys") == ("robot", "holding keys")
    assert pixel.split_mode("ícone") == ("icon", "")
    assert pixel.split_mode("a red car") == (None, "a red car")
    assert "no robot" in pixel.subject_for_unknown("Finance Bot", "bills", "icon")
    assert "robot character" in pixel.subject_for_unknown("Finance Bot", "bills", "robot")


def test_generated_avatar_path_accepts_only_plugin_output(tmp_path):
    cache = tmp_path / "cache" / "generated" / "images"
    cache.mkdir(parents=True)
    avatar = cache / "avatar_pixel_20261102_120000_abcdef12.png"
    Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(avatar)
    assert pixel.generated_avatar_path(str(avatar), cache) == avatar

    other = tmp_path / avatar.name
    other.write_bytes(b"png")
    unrelated = cache / "other_20261102_120000_abcdef12.png"
    unrelated.write_bytes(b"png")
    link = cache / "avatar_pixel_20261102_120001_abcdef12.png"
    link.symlink_to(other)
    invalid_png = cache / "avatar_pixel_20261102_120002_abcdef12.png"
    invalid_png.write_bytes(b"not a PNG")
    for image in (other, unrelated, link, invalid_png, cache / "missing.png"):
        with pytest.raises(ValueError):
            pixel.generated_avatar_path(str(image), cache)
