# app/templating.py
from pathlib import Path

from fastapi.templating import Jinja2Templates

# Bump app/VERSION on every deploy build. It is shown as "vN" in the footer and
# appended to static asset URLs (?v=N) so Cloudflare and browsers fetch fresh copies.
APP_VERSION = (Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip()

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["app_version"] = APP_VERSION
