"""增加逐袋交接与配送追踪表。

Revision ID: 0002_parcel_traceability
Revises: 0001_initial
"""

from alembic import op

from backend.app.database import Base
from backend.app import models  # noqa: F401 - 注册全部模型元数据


revision = "0002_parcel_traceability"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


TABLE_NAMES = ("pickup_handoff_parcels", "delivery_task_parcels")


def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLE_NAMES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(TABLE_NAMES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
