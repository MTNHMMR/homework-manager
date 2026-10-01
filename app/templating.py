# app/templating.py
from pathlib import Path

from fastapi.templating import Jinja2Templates

# app/VERSION is the visual design version, shown as "vN" in the footer and
# appended to static asset URLs (?v=N). Bump it whenever app/static/ changes so
# Cloudflare and browsers fetch fresh copies; feature-only deploys keep it.
APP_VERSION = (Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip()

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["app_version"] = APP_VERSION
