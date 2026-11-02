"""avatar-pixel: pixel art avatars for Hermes agents (profiles), in one shared style.

Two entry points:
- an image-gen backend (``image_gen.provider: avatar-pixel``) that answers the Hermes Desktop's
  Edit profile -> Generate requests with a transparent pixel art sprite; every other image request
  passes straight through to the delegate backend (``openai-codex`` by default);
- the ``agent_avatar`` tool, so an agent can draw (and, when asked, apply) the avatar of any profile.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent.image_gen_provider import (DEFAULT_ASPECT_RATIO, ImageGenProvider, resolve_aspect_ratio,
                                      save_b64_image, success_response)

from . import pixel

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
STYLE_REFS = sorted((HERE / "assets" / "style").glob("*.png"))
PROVIDER_ID = "avatar-pixel"
TOOLSET = "avatar_pixel"


# --- configuration --------------------------------------------------------------------------------
def _hermes_root() -> Optional[Path]:
    try:
        from hermes_constants import get_default_hermes_root
        return Path(get_default_hermes_root())
    except Exception:
        return None


def _catalog_path() -> Optional[Path]:
    """AVATAR_PIXEL_CATALOG, else <hermes root>/avatar-pixel/catalog.json (shared by all profiles)."""
    env = os.environ.get("AVATAR_PIXEL_CATALOG", "").strip()
    if env:
        return Path(env).expanduser()
    root = _hermes_root()
    return root / "avatar-pixel" / "catalog.json" if root else None


def _load_catalog() -> tuple[dict, Path]:
    path = _catalog_path()
    if not path or not path.is_file():
        return {}, HERE
    try:
        real = path.resolve()
        return json.loads(real.read_text(encoding="utf-8")), real.parent
    except Exception as exc:
        logger.warning("avatar-pixel: could not read catalog %s: %s", path, exc)
        return {}, HERE


@contextmanager
def _secret_scope():
    """Bind the current profile's secret scope when none is active.

    On a multiplexed gateway (several profiles in one process) Hermes fails closed on secret reads
    outside a profile scope, and the Desktop's ``image.generate`` RPC runs unscoped: the Codex
    credential lookup raises UnscopedSecretError, so every image backend reports unavailable
    ("No image model available"). Scoping here keeps the delegate usable from that RPC."""
    token = None
    try:
        from agent import secret_scope as ss
        if ss.is_multiplex_active() and ss.current_secret_scope() is None:
            from hermes_constants import get_hermes_home
            home = Path(get_hermes_home())
            token = ss.set_secret_scope(ss.build_profile_secret_scope(home), profile_home=str(home))
    except Exception:
        logger.debug("avatar-pixel: could not bind a secret scope", exc_info=True)
        token = None
    try:
        yield
    finally:
        if token is not None:
            from agent import secret_scope as ss
            ss.reset_secret_scope(token)


def _delegate_id() -> str:
    return os.environ.get("AVATAR_PIXEL_DELEGATE", "").strip() or "openai-codex"


def _delegate() -> Optional[ImageGenProvider]:
    from agent.image_gen_registry import get_provider
    p = get_provider(_delegate_id())
    return None if p is None or getattr(p, "name", None) == PROVIDER_ID else p


def _error(message: str, error_type: str, prompt: str, aspect: str) -> dict[str, Any]:
    return {"success": False, "image": None, "error": message, "error_type": error_type,
            "provider": PROVIDER_ID, "prompt": prompt, "aspect_ratio": aspect}


# --- profiles -------------------------------------------------------------------------------------
def _profile_dir(profile: str) -> Path:
    from hermes_cli.profiles import get_profile_dir
    return Path(get_profile_dir(profile))


def _yaml():
    try:
        import hermes_yaml as y  # Hermes ships its own YAML module; PyYAML may be missing
    except ImportError:
        import yaml as y
    return y


def _profile_meta(profile: str) -> dict:
    path = _profile_dir(profile) / "profile.yaml"
    if not path.is_file():
        return {}
    return _yaml().safe_load(path.read_text(encoding="utf-8")) or {}


def _profile_identity(profile: str) -> tuple[str, str]:
    meta = _profile_meta(profile)
    bots = (meta.get("ui_meta") or {}).get("hermes-bots") or {}
    title = bots.get("title") or meta.get("display_name") or profile
    return str(title), str(meta.get("description") or "").strip()


# --- the avatar itself ----------------------------------------------------------------------------
def _default_mode() -> str:
    return pixel.normalize_mode(os.environ.get("AVATAR_PIXEL_MODE")) or pixel.DEFAULT_MODE


def make_avatar(*, title: str = "", description: str = "", details: str = "", subject: str = "",
                profile: str = "", mode: str = "", prompt_for_result: str = "") -> dict[str, Any]:
    """Draw one avatar and return an image_gen result dict (``image`` is a PNG path in the cache).

    Subject, in order: ``subject`` as given; with an explicit ``mode`` (icon|robot), the agent's role
    in that mode, using the catalog subject only as a theme; the catalog entry (by profile id or
    title); otherwise the agent's role in the default mode. ``details`` is always appended."""
    from PIL import Image

    catalog, base = _load_catalog()
    entry = (pixel.find_catalog_entry(catalog, profile) if profile else None) \
        or (pixel.find_catalog_entry(catalog, title) if title else None) or {}
    shown_prompt = prompt_for_result or f"avatar: {title or profile or subject}"
    mode = pixel.normalize_mode(mode) or ""
    custom = bool(details or subject or mode)

    fixed = pixel.entry_field(entry, "image", "solto_fixo")
    if fixed and not custom:  # hand-made avatar: return it as is
        return _save(Image.open(base / fixed).convert("RGBA"), shown_prompt, "fixed", {"source": str(fixed)})

    raw_fixed = pixel.entry_field(entry, "raw", "sprite_fixo")
    if raw_fixed and not custom:
        raw, used = Image.open(base / raw_fixed), "fixed-raw"
    else:
        delegate = _delegate()
        if delegate is None:
            raise RuntimeError(f"delegate image backend '{_delegate_id()}' is not registered")
        catalog_subject = pixel.entry_field(entry, "subject", "assunto") or ""
        name = title or profile or "agent"
        if subject:
            main = subject
        elif mode:
            main = pixel.subject_for_unknown(name, description, mode, theme=catalog_subject)
        else:
            main = catalog_subject or pixel.subject_for_unknown(name, description, _default_mode())
        if details:
            main = f"{main}. Extra direction from the user: {details}"
        refs = pixel.resolve_paths(base, pixel.entry_field(entry, "references", "referencias"))
        r = delegate.generate(pixel.build_prompt(main, len(STYLE_REFS), bool(refs)), "square",
                              reference_image_urls=[str(p) for p in STYLE_REFS + refs])
        if not r.get("success") or not r.get("image"):
            return r
        raw, used = Image.open(r["image"]), r.get("model") or _delegate_id()
    sprite = pixel.fit_square(pixel.remove_background(raw, pixel.entry_field(entry, "holes", "furos")))
    return _save(sprite, shown_prompt, used, {"catalog_entry": bool(entry)})


def _save(sprite, prompt: str, model: str, extra: dict) -> dict[str, Any]:
    buf = io.BytesIO()
    sprite.save(buf, "PNG")
    path = save_b64_image(base64.b64encode(buf.getvalue()).decode("ascii"), prefix="avatar_pixel")
    return success_response(image=str(path), model=model, prompt=prompt, aspect_ratio="square",
                            provider=PROVIDER_ID, extra=extra)


def apply_avatar(profile: str, image: Path) -> Path:
    """Install ``image`` as the profile's avatar, exactly like the Desktop's Upload tab does:
    assets/avatar.png plus ui_meta.hermes-bots.imageKind=photo and a bumped revision. Old files are
    kept with a .bak-avatar-<timestamp> suffix."""
    home = _profile_dir(profile)
    if not home.is_dir():
        raise FileNotFoundError(f"profile '{profile}' does not exist")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    assets = home / "assets"
    assets.mkdir(exist_ok=True)
    for ext in ("png", "jpg", "webp"):
        old = assets / f"avatar.{ext}"
        if old.is_file():
            old.rename(assets / f"avatar.{ext}.bak-avatar-{stamp}")
    tmp = assets / "avatar.png.tmp"
    shutil.copyfile(image, tmp)
    tmp.replace(assets / "avatar.png")

    y = _yaml()
    meta_path = home / "profile.yaml"
    meta = {}
    if meta_path.is_file():
        shutil.copyfile(meta_path, home / f"profile.yaml.bak-avatar-{stamp}")
        meta = y.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    bots = meta.setdefault("ui_meta", {}).setdefault("hermes-bots", {})
    bots["imageKind"] = "photo"
    bots["custom"] = True
    revs = meta.setdefault("_ui_meta_revisions", {})
    revs["hermes-bots"] = int(revs.get("hermes-bots", 0) or 0) + 1
    meta_path.write_text(y.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return assets / "avatar.png"


def _scoped_profile() -> str:
    """Profile whose HERMES_HOME the current request is bound to ('' when unknown)."""
    try:
        from hermes_constants import get_hermes_home
        home, root = Path(get_hermes_home()).resolve(), _hermes_root()
        if root and home == root.resolve():
            return "default"
        if home.parent.name == "profiles":
            return home.name
    except Exception:
        pass
    return ""


# --- image-gen backend ----------------------------------------------------------------------------
class AvatarPixelProvider(ImageGenProvider):
    """Pixel art avatars for the Desktop's Generate tab; everything else goes to the delegate."""

    @property
    def name(self) -> str:
        return PROVIDER_ID

    @property
    def display_name(self) -> str:
        return "Avatar Pixel (pixel art avatars)"

    def is_available(self) -> bool:
        d = _delegate()
        with _secret_scope():
            return bool(d and d.is_available())

    def capabilities(self) -> dict[str, Any]:
        d = _delegate()
        return d.capabilities() if d else super().capabilities()

    def list_models(self) -> list[dict[str, Any]]:
        d = _delegate()
        return d.list_models() if d else []

    def default_model(self) -> Optional[str]:
        d = _delegate()
        return d.default_model() if d else None

    def get_setup_schema(self) -> dict[str, Any]:
        d = _delegate()
        schema = dict(d.get_setup_schema()) if d else {"env_vars": []}
        schema.update(name=self.display_name,
                      tag=f"Pixel art avatars for Edit profile -> Generate; other images via {_delegate_id()}")
        return schema

    def generate(self, prompt: str, aspect_ratio: str = DEFAULT_ASPECT_RATIO, *,
                 image_url: Optional[str] = None, reference_image_urls: Optional[list[str]] = None,
                 **kwargs: Any) -> dict[str, Any]:
        with _secret_scope():
            return self._generate(prompt, aspect_ratio, image_url=image_url,
                                  reference_image_urls=reference_image_urls, **kwargs)

    def _generate(self, prompt: str, aspect_ratio: str = DEFAULT_ASPECT_RATIO, *,
                  image_url: Optional[str] = None, reference_image_urls: Optional[list[str]] = None,
                  **kwargs: Any) -> dict[str, Any]:
        request = None if image_url else pixel.parse_avatar_prompt(prompt or "")
        if request is None:
            delegate = _delegate()
            if delegate is None:
                return _error(f"avatar-pixel: delegate image backend '{_delegate_id()}' is not registered",
                              "provider_not_registered", prompt, resolve_aspect_ratio(aspect_ratio))
            return delegate.generate(prompt, aspect_ratio, image_url=image_url,
                                     reference_image_urls=reference_image_urls, **kwargs)
        scoped = _scoped_profile()
        logger.info("avatar-pixel: desktop request %s (request scope: %s)", request, scoped or "?")
        try:
            if "title" in request:
                return make_avatar(title=request["title"], description=request["description"],
                                   prompt_for_result=prompt)
            return self._typed(request["text"], prompt)
        except Exception as exc:
            logger.warning("avatar-pixel failed", exc_info=True)
            return _error(f"avatar-pixel: {exc}", "api_error", prompt, "square")

    @staticmethod
    def _typed(text: str, prompt: str) -> dict[str, Any]:
        """Text typed in the Generate box. ``Name: what to draw`` (or ``profile-id: ...``) names the
        bot, so its catalog entry and description are used and the text becomes extra direction;
        plain text is drawn as the subject."""
        title, sep, rest = text.partition(":")
        if sep and rest.strip() and 0 < len(title.strip()) <= 60:
            name = title.strip()
            profile, description = "", ""
            try:
                if _profile_dir(name.lower()).is_dir():
                    profile = name.lower()
                    name, description = _profile_identity(profile)
            except Exception:
                pass
            mode, details = pixel.split_mode(rest)
            return make_avatar(title=name, description=description, profile=profile, mode=mode or "",
                               details=details, prompt_for_result=prompt)
        mode, rest = pixel.split_mode(text)
        if mode == "robot" and rest:
            text = f"a small cute robot character: {rest}"
        elif mode == "icon" and rest:
            text = f"{rest}. An object only: no character, no robot, no face"
        return make_avatar(subject=text, prompt_for_result=prompt)


# --- agent tool -----------------------------------------------------------------------------------
TOOL_SCHEMA = {
    "name": "agent_avatar",
    "description": (
        "Draw the avatar of a Hermes agent (profile) as a transparent pixel art sprite in the house "
        "style, and optionally install it as that profile's avatar (what the Desktop shows). Without "
        "'apply' it only returns the image path: show it to the user and apply only after they approve. "
        "To apply an image that was already approved, pass it in 'image' with apply=true (no new drawing)."),
    "parameters": {
        "type": "object",
        "properties": {
            "profile": {"type": "string", "description": "Profile id, e.g. 'default', 'finance'"},
            "details": {"type": "string", "description": "Optional extra direction for the drawing, e.g. "
                        "'a piggy bank wearing glasses'. Combined with the profile's name and description."},
            "subject": {"type": "string", "description": "Optional: replace the subject entirely (English)."},
            "mode": {"type": "string", "enum": ["icon", "robot"], "description":
                     "icon: a single object, like an app icon. robot: a small robot character personifying "
                     "the agent. Omit to keep the profile's catalog subject (or the default mode)."},
            "image": {"type": "string", "description": "Path of an avatar generated by this plugin to apply."},
            "apply": {"type": "boolean", "description": "Install as the profile's avatar. Default false."},
        },
        "required": ["profile"],
    },
}


def agent_avatar(args: dict, **_kw) -> str:
    profile = str(args.get("profile") or "").strip()
    if not profile:
        return json.dumps({"success": False, "error": "profile is required"})
    try:
        if not _profile_dir(profile).is_dir():
            return json.dumps({"success": False, "error": f"profile '{profile}' does not exist"})
        image = str(args.get("image") or "").strip()
        if not image:
            title, description = _profile_identity(profile)
            r = make_avatar(title=title, description=description, profile=profile,
                            details=str(args.get("details") or "").strip(),
                            subject=str(args.get("subject") or "").strip(),
                            mode=str(args.get("mode") or "").strip())
            if not r.get("success"):
                return json.dumps({"success": False, "error": r.get("error") or "generation failed"})
            image = r["image"]
        from hermes_constants import get_hermes_home
        cache_dir = Path(get_hermes_home()) / "cache" / "generated" / "images"
        image_path = pixel.generated_avatar_path(image, cache_dir)
        result = {"success": True, "profile": profile, "image": str(image_path), "applied": False}
        if args.get("apply"):
            result.update(applied=True, avatar=str(apply_avatar(profile, image_path)),
                          note="Desktop clients that cached the old picture keep it until re-uploaded or cache cleared.")
        else:
            result["next"] = "Show the image to the user; call again with image=<path> and apply=true once approved."
        return json.dumps(result)
    except Exception as exc:
        logger.warning("agent_avatar failed", exc_info=True)
        return json.dumps({"success": False, "error": str(exc)})


def register(ctx) -> None:
    ctx.register_image_gen_provider(AvatarPixelProvider())
    ctx.register_tool(name=TOOL_SCHEMA["name"], toolset=TOOLSET, schema=TOOL_SCHEMA, handler=agent_avatar,
                      description=TOOL_SCHEMA["description"], emoji="🎨")
