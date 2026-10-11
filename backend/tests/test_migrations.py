from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_alembic_builds_schema_from_empty_database(workspace_test_dir, monkeypatch):
    project_root = Path(__file__).resolve().parents[2]
    database_path = (workspace_test_dir / "migration.db").as_posix()
    config = Config(str(project_root / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    tables = set(inspect(engine).get_table_names())
    assert {
        "orders",
        "order_items",
        "parcels",
        "batches",
        "pickup_stops",
        "pickup_handoffs",
        "pickup_handoff_parcels",
        "pickup_early_close_authorizations",
        "demo_clocks",
        "delivery_task_parcels",
        "issues",
        "audit_logs",
        "idempotency_records",
        "alembic_version",
    }.issubset(tables)
    with engine.connect() as connection:
        assert connection.execute(text("select version_num from alembic_version")).scalar_one() == "0004_pickup_deadlines_clock"
        assert connection.execute(text("select count(*) from orders")).scalar_one() == 0
    order_item_columns = {column["name"]: column for column in inspect(engine).get_columns("order_items")}
    assert order_item_columns["product_name"]["nullable"] is False
    pickup_stop_columns = {column["name"]: column for column in inspect(engine).get_columns("pickup_stops")}
    assert pickup_stop_columns["latest_handoff_at"]["nullable"] is False
    engine.dispose()
