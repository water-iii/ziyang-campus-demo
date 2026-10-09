from __future__ import annotations

import os
from pathlib import Path

from .app import models  # noqa: F401 - 注册模型
from .app.database import Base, build_engine, build_session_factory
from .app.seed import seed_demo_data


def database_url() -> str:
    configured = os.getenv("DATABASE_URL")
    if configured:
        return configured
    path = Path(__file__).resolve().parent / "data" / "demo.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def main() -> None:
    engine = build_engine(database_url())
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    with session_factory.begin() as db:
        result = seed_demo_data(db, reset=True)
    engine.dispose()
    print(
        f"RESET_OK batch={result['batch_id']} orders={result['orders']} "
        f"parcels={result['parcels']} merchants={result['merchants']}"
    )


if __name__ == "__main__":
    main()
