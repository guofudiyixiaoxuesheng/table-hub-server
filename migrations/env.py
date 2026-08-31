"""Alembic 异步迁移环境。"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.core.database import Base
from app.modules.auth.models import (  # noqa: F401
    RefreshToken,
    Store,
    StoreInvite,
    StoreMember,
)
from app.modules.chat.models import ChatMessage, ChatSession  # noqa: F401
from app.modules.idempotency.models import IdempotencyRecord  # noqa: F401
from app.modules.knowledge.models import KnowledgeDocument  # noqa: F401
from app.modules.user.models import User  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    """忽略由 PostGIS 扩展维护的系统表。"""

    langgraph_tables = {
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
    }
    if type_ == "table" and name in {"spatial_ref_sys", *langgraph_tables}:
        return False
    return not (type_ == "index" and name.startswith("checkpoint_"))


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
