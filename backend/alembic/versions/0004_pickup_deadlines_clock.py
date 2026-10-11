"""增加站点最晚交接、Demo 时钟与提前关闭授权。

Revision ID: 0004_pickup_deadlines_clock
Revises: 0003_order_item_snapshot
"""

from datetime import datetime, timedelta

from alembic import op
import sqlalchemy as sa

from backend.app import models  # noqa: F401 - 注册新增表
from backend.app.database import Base


revision = "0004_pickup_deadlines_clock"
down_revision = "0003_order_item_snapshot"
branch_labels = None
depends_on = None


NEW_TABLES = ("demo_clocks", "pickup_early_close_authorizations")
LOADING_BUFFER_MINUTES = 5


def _columns(table_name: str) -> dict[str, dict]:
    bind = op.get_bind()
    return {column["name"]: column for column in sa.inspect(bind).get_columns(table_name)}


def _datetime(value: datetime | str) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in NEW_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)

    columns = _columns("pickup_stops")
    if "latest_handoff_at" not in columns:
        op.add_column("pickup_stops", sa.Column("latest_handoff_at", sa.DateTime(), nullable=True))

    rows = bind.execute(
        sa.text(
            """
            SELECT pickup_stops.id, pickup_stops.planned_pickup_at, batches.depart_at
            FROM pickup_stops
            JOIN pickup_routes ON pickup_routes.id = pickup_stops.route_id
            JOIN batches ON batches.id = pickup_routes.batch_id
            WHERE pickup_stops.latest_handoff_at IS NULL
            """
        )
    ).mappings()
    for row in rows:
        planned_at = _datetime(row["planned_pickup_at"])
        depart_at = _datetime(row["depart_at"])
        departure_safe_at = depart_at - timedelta(minutes=LOADING_BUFFER_MINUTES)
        if planned_at > departure_safe_at:
            raise RuntimeError(
                f"站点 {row['id']} 的预计到店时间未预留 {LOADING_BUFFER_MINUTES} 分钟装车缓冲。"
            )
        latest_handoff_at = min(planned_at + timedelta(minutes=5), departure_safe_at)
        bind.execute(
            sa.text(
                "UPDATE pickup_stops SET latest_handoff_at = :latest_handoff_at WHERE id = :stop_id"
            ),
            {"latest_handoff_at": latest_handoff_at, "stop_id": row["id"]},
        )

    columns = _columns("pickup_stops")
    if columns["latest_handoff_at"].get("nullable", True):
        with op.batch_alter_table("pickup_stops") as batch_op:
            batch_op.alter_column(
                "latest_handoff_at",
                existing_type=sa.DateTime(),
                nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(NEW_TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)
    if "latest_handoff_at" in _columns("pickup_stops"):
        with op.batch_alter_table("pickup_stops") as batch_op:
            batch_op.drop_column("latest_handoff_at")
