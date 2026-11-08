"""Shared mutation locks for REST and MCP operations."""

import asyncio

_playlist_locks: dict[str, asyncio.Lock] = {}


def playlist_mutation_lock(playlist_id: str) -> asyncio.Lock:
    """Return the process-wide lock for a case-insensitive playlist identity."""
    key = playlist_id.casefold()
    return _playlist_locks.setdefault(key, asyncio.Lock())
