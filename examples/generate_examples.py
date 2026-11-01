"""Regenerate the example gallery: runs each examples.json entry through the plugin exactly as the
Hermes Desktop Generate button would (no catalog entry, so the subject comes from the description).

    cd <plugin dir> && /opt/hermes/.venv/bin/python examples/generate_examples.py icon|robot [name ...]

Images go to examples/<mode>/<name>.png.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, "/opt/hermes")

from hermes_cli.plugins import _ensure_plugins_discovered  # noqa: E402

spec = importlib.util.spec_from_file_location("avatar_pixel_examples", ROOT / "__init__.py",
                                              submodule_search_locations=[str(ROOT)])
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)


def run(name: str, item: dict, mode: str) -> str:
    prompt = (f'Cute minimal robot avatar for an AI agent named "{item["title"]} — {item["description"]}". '
              "Friendly simple mascot face, bold flat vector style, solid color background, centered, no text.")
    if mode == "icon":  # the Desktop button with an empty box, default mode
        r = plugin.AvatarPixelProvider().generate(prompt, "square")
    else:
        r = plugin.make_avatar(title=item["title"], description=item["description"], mode=mode)
    if not r.get("success"):
        return f"{name}: FAILED {r.get('error')}"
    (HERE / mode).mkdir(exist_ok=True)
    shutil.copy(r["image"], HERE / mode / f"{name}.png")
    return f"{name}: ok"


def main() -> None:
    _ensure_plugins_discovered()
    items = json.loads((HERE / "examples.json").read_text())
    mode, names = sys.argv[1], sys.argv[2:] or list(items)
    with ThreadPoolExecutor(4) as pool:
        for line in pool.map(lambda n: run(n, items[n], mode), names):
            print(line, flush=True)


if __name__ == "__main__":
    main()
