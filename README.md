# avatar-pixel

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin that gives every agent (profile) a pixel art avatar, all drawn in the same style.

- **Hermes Desktop:** *Edit profile → Generate* (also when creating a bot) returns a transparent pixel art sprite instead of the generic robot face.
- **Agents:** the `agent_avatar` tool lets an agent draw the avatar of any profile, show it to you, and install it once you approve.
- **Everything else is untouched:** any other image request passes straight through to the delegate backend (`openai-codex` by default), so `image_generate` keeps working as before.

## Examples

Generated from the agent's name and description only, exactly as the Generate button does (`examples/examples.json`):

| | | | |
|:-:|:-:|:-:|:-:|
| ![](examples/finance-bot.png)<br>Finance Bot | ![](examples/my-health-bot.png)<br>My Health Bot | ![](examples/developer-bot.png)<br>Developer Bot | ![](examples/shopping-assistant.png)<br>Shopping Assistant |
| ![](examples/travel-planner.png)<br>Travel Planner | ![](examples/meal-prep-chef.png)<br>Meal Prep Chef | ![](examples/car-care-bot.png)<br>Car Care Bot | ![](examples/smart-home-bot.png)<br>Smart Home Bot |
| ![](examples/fitness-coach.png)<br>Fitness Coach | ![](examples/study-buddy.png)<br>Study Buddy | ![](examples/inbox-triage.png)<br>Inbox Triage | ![](examples/plant-care-bot.png)<br>Plant Care Bot |
| ![](examples/pet-care-bot.png)<br>Pet Care Bot | ![](examples/security-watch.png)<br>Security Watch | ![](examples/music-dj.png)<br>Music DJ | ![](examples/calendar-assistant.png)<br>Calendar Assistant |

## How it works

1. The style lives in `assets/style/` (three approved sprites sent as reference images) and in `STYLE_PROMPT` (`pixel.py`): chunky pixels, dark 1-pixel outline, flat colors, chibi proportions, no text.
2. The model draws on a flat magenta background; the plugin keys it out (falling back to a flood fill when the model returns white), crops to the sprite and scales it with nearest neighbour to fill a 512×512 square.
3. The result is a transparent PNG, so it looks right in light and dark themes.

## Install

```bash
git clone https://github.com/BrOrlandi/hermes-avatar-pixel-plugin ~/.hermes/plugins/avatar-pixel
hermes plugins enable avatar-pixel
hermes config set image_gen.provider avatar-pixel        # in every profile that should use it
hermes gateway restart
```

Requires an image backend that accepts reference images (`openai-codex` with gpt-image-2 works without an API key: `hermes auth add openai-codex`). Pick another with `AVATAR_PIXEL_DELEGATE`.

Hermes Desktop reads the image backend of the profile it is talking to, so set `image_gen.provider` in each profile (or the Generate tab says "No image model available").

## Using it

**Generate tab** (Edit profile or Create bot):

| You type | What is drawn |
|---|---|
| nothing | a symbol picked from the bot's name and description (or its catalog entry) |
| `a red sports car` | exactly that |
| `Finance Bot: a piggy bank with glasses` or `<profile-id>: ...` | that bot (catalog entry, description) with your text as extra direction |

**Agents:** ask your main agent something like *"make a new avatar for the finance profile, with a piggy bank"*. It calls `agent_avatar(profile="finance", details="a piggy bank")`, sends you the picture, and calls it again with `image=<path>, apply=true` after you approve. The `avatar_pixel` toolset must be enabled for that agent (`hermes tools`).

## Catalog (optional)

Fix the subject, reference images or a hand-made avatar per profile in `<hermes root>/avatar-pixel/catalog.json` (or `AVATAR_PIXEL_CATALOG`). Paths are relative to the catalog file.

```json
{
  "finance": {"name": "Finance Bot", "subject": "a gold coin with a dollar sign next to a rising green chart"},
  "coffee":  {"name": "Coffee Shop", "subject": "the cat mascot from the reference photo", "references": ["refs/cat.png"]},
  "default": {"name": "Main", "image": "fixed/main.png"}
}
```

| Field | Meaning |
|---|---|
| `name` | Matches the bot title the Desktop sends |
| `subject` | What to draw, in English (one concrete sentence) |
| `references` | Extra reference images showing what the subject looks like (logos, mascots) |
| `image` | Hand-made transparent avatar returned as is |
| `holes` | `[x, y]` seeds for the white-background fallback, for enclosed gaps |

## Development

```bash
python -m pytest tests                                          # pure helpers, needs Pillow
/opt/hermes/.venv/bin/python examples/generate_examples.py      # regenerate the gallery (inside Hermes)
```

## License

MIT
