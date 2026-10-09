"""初始化 Stage 1 数据结构。

Revision ID: 0001_initial
Revises: None
"""

from alembic import op

from backend.app.database import Base
from backend.app import models  # noqa: F401 - 注册全部模型元数据


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        table.drop(bind=bind, checkfirst=True)
