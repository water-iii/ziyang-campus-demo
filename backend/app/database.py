from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str) -> Engine:
    options: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            options["poolclass"] = StaticPool
    engine = create_engine(database_url, **options)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return engine


def build_session_factory(engine: Engine, app_env: str = "demo") -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        info={"app_env": app_env},
    )


def get_db(request: Request) -> Generator[Session, None, None]:
    db: Session = request.app.state.session_factory()
    try:
        # SQLite 的默认 deferred transaction 会让两个并发下单请求先读到相同
        # 容量快照，再在升级写锁时产生竞态或 database is locked。写请求先取得
        # RESERVED 锁，使容量检查、UUID 主键写入和审计处于同一串行事务。
        if request.method not in {"GET", "HEAD", "OPTIONS"} and db.get_bind().dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
