"""Backward-compatible entry point; the implementation lives in campuspilot.app."""

import os

# Tests patch campuspilot.web.httpx.AsyncClient; keep the module attribute.
import httpx as httpx

from campuspilot.app.factory import create_web_app as create_web_app
from campuspilot.app.main import app_factory as app_factory
from campuspilot.app.main import main as main
from campuspilot.app.main import model_from_env as model_from_env
from campuspilot.app.state import ASSETS as ASSETS
from campuspilot.app.state import COOKIE as COOKIE
from campuspilot.app.state import NOTICE as NOTICE
from campuspilot.app.state import BrowserSession as BrowserSession
from campuspilot.app.validation import ChatInput as ChatInput
from campuspilot.app.validation import validate_place_params as validate_place_params
from campuspilot.app.validation import validate_route_params as validate_route_params
from campuspilot.chat_runtime import Mode
from campuspilot.config import parse_mode


def runtime_mode_from_env() -> Mode:
    return parse_mode(os.environ.get("CAMPUSPILOT_RUNTIME_MODE", "legacy"))


if __name__ == "__main__":
    main()
