from __future__ import annotations

import os
import re
from typing import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

Base = declarative_base()

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    # pool_pre_ping recycles connections that a database restart or an idle
    # timeout left dead, which otherwise surfaces as InterfaceError on the
    # first query after an outage. pool_recycle bounds connection age for
    # proxies that silently drop idle sessions.
    pool_pre_ping=True,
    **({} if _is_sqlite else {"pool_size": 10, "max_overflow": 20, "pool_recycle": 1800}),
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Request-scoped session with guaranteed rollback on failure.

    The previous generator only closed the session, so a failed request could
    leave uncommitted state in the session and the next use in the same
    connection would observe it.
    """
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    if _is_sqlite:
        # sqlalchemy's make_url is the correct parser here. A naive
        # urlparse(...).path on a Windows DSN such as
        # sqlite+aiosqlite:///C:/data/app.db yields "/C:/data/app.db", and
        # os.path.abspath then collapses it to the invalid "C:\C:\data".
        raw = make_url(settings.DATABASE_URL).database or ""
        path = raw[1:] if re.match(r"^/[A-Za-z]:", raw) else raw
        if path:
            directory = os.path.dirname(os.path.abspath(path))
            if directory:
                os.makedirs(directory, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
    logger.info("database schema ensured", extra={"context": {"backend": engine.dialect.name}})


def _add_missing_columns(connection) -> None:
    """Additive column migration.

    ``create_all`` never alters an existing table, so any database created
    before a column was added keeps the old shape and every insert of that
    column fails at runtime. This walks the existing tables and issues
    ``ALTER TABLE ... ADD COLUMN`` for any column the models declare but the
    file does not have yet.

    This is deliberately additive-only: SQLite cannot drop or retype columns,
    and destructive schema changes should be an explicit, reviewed operation
    rather than a side effect of application startup.
    """
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # created by create_all above
        present = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            ddl = _add_column_ddl(table.name, column, connection.dialect)
            if ddl is None:
                continue
            logger.info(
                "adding missing column",
                extra={"context": {"table": table.name, "column": column.name}},
            )
            connection.execute(text(ddl))


def _add_column_ddl(table_name: str, column, dialect) -> Optional[str]:
    """Render an ADD COLUMN statement, or None when the type cannot be added.

    A NOT NULL column without a server default cannot be added to a table that
    already holds rows, so those are skipped and reported instead of crashing
    startup.
    """
    try:
        column_type = column.type.compile(dialect=dialect)
    except Exception:
        return None

    parts = [f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}"', column_type]
    default = getattr(column.server_default, "arg", None)
    if default is not None:
        parts.append(f"DEFAULT {default}")
    elif not column.nullable and not column.primary_key:
        # Would fail on a non-empty table. Skip rather than break startup.
        logger.warning(
            "cannot add non-nullable column without default; skipping",
            extra={"context": {"table": table_name, "column": column.name}},
        )
        return None
    return " ".join(parts)


async def dispose_db() -> None:
    await engine.dispose()

