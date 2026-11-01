"""ASGI entry point retained for the existing `server:app` launcher."""

from api.app import app

__all__ = ["app"]
