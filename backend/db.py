"""Couche base de donnees (SQLite + SQLAlchemy async)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# Migrations legeres : (table, colonne) -> definition SQL pour SQLite ALTER TABLE.
_LIGHT_MIGRATIONS: list[tuple[str, str, str]] = [
    ("bets", "strategy", "VARCHAR(16) NOT NULL DEFAULT 'candle'"),
]


async def init_db() -> None:
    """Cree les tables et applique les migrations legeres en place."""
    # Import to ensure models are registered with Base.metadata
    from backend import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def _existing_columns(sync_conn, table: str) -> set[str]:
            insp = inspect(sync_conn)
            if not insp.has_table(table):
                return set()
            return {col["name"] for col in insp.get_columns(table)}

        for table, column, ddl in _LIGHT_MIGRATIONS:
            cols = await conn.run_sync(_existing_columns, table)
            if not cols or column in cols:
                continue
            logger.info("Migration legere : ALTER %s ADD %s", table, column)
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
