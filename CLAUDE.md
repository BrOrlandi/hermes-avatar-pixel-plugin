# avatar-pixel

Hermes Agent plugin: pixel art avatars for agents (image-gen backend + `agent_avatar` tool). Code in `__init__.py` (Hermes glue) and `pixel.py` (pure helpers, tested in `tests/`). Runs inside Hermes, so test against a real install (`/opt/hermes/.venv/bin/python`).

## Release & Changelog

Structured convention: `.claude/release.json` (read by the `release` skill).

- Version lives only in `plugin.yaml` (`version`), which is what `hermes plugins list` shows.
- Changelog: `CHANGELOG.md` (Keep a Changelog, English, public). Add entries under `[Unreleased]` as changes land; move them under the new version when releasing.
- Release: bump `plugin.yaml`, date the changelog section, commit `chore(release): vX.Y.Z`, annotated tag `vX.Y.Z`, push, then `gh release create vX.Y.Z --notes-file <that version's changelog section>`.
- SemVer: breaking change to the tool schema, catalog format or Generate prompt syntax → major; new feature → minor; fix → patch. Confirm the bump with the maintainer.
- Installs update with `hermes plugins update avatar-pixel`.
