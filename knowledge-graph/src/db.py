"""
Async PostgreSQL connection pool for the knowledge graph.

The pool is created lazily and bound to the running event loop.
If the loop changes (e.g. between pytest functions), the stale pool
is discarded and a fresh one is created automatically.

Connects to Azure Database for PostgreSQL Flexible Server with SSL.
"""

from __future__ import annotations

import asyncio
import os
import ssl
import logging

import asyncpg
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("kg.db")

_pool: asyncpg.Pool | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None


def _create_ssl_context() -> ssl.SSLContext:
    """Create an SSL context for Azure PostgreSQL connections."""
    ctx = ssl.create_default_context()
    return ctx


async def get_pool() -> asyncpg.Pool:
    """Return (and lazily create) the shared connection pool.

    Automatically recreates the pool when the event loop has changed
    (common in per-test-function pytest-asyncio configurations).
    """
    global _pool, _pool_loop

    loop = asyncio.get_running_loop()

    if _pool is not None and _pool_loop is not loop:
        # Pool belongs to a dead loop — discard it
        logger.debug("Event loop changed; discarding stale pool")
        _pool = None
        _pool_loop = None

    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=os.getenv("PG_HOST", "localhost"),
            port=int(os.getenv("PG_PORT", "5432")),
            user=os.getenv("PG_USER", "pgadmin"),
            password=os.getenv("PG_PASSWORD", ""),
            database=os.getenv("PG_DATABASE", "appdb"),
            ssl=_create_ssl_context(),
            min_size=1,
            max_size=10,
        )
        _pool_loop = loop
        logger.info("PG pool created")
    return _pool


async def close_pool() -> None:
    """Close the connection pool."""
    global _pool, _pool_loop
    if _pool:
        try:
            await _pool.close()
        except Exception:
            pass
        _pool = None
        _pool_loop = None
        logger.info("PG pool closed")
