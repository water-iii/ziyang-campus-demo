"""固化订单商品名称快照。

Revision ID: 0003_order_item_snapshot
Revises: 0002_parcel_traceability
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_order_item_snapshot"
down_revision = "0002_parcel_traceability"
branch_labels = None
depends_on = None


def _columns() -> dict[str, dict]:
    bind = op.get_bind()
    return {column["name"]: column for column in sa.inspect(bind).get_columns("order_items")}


def upgrade() -> None:
    columns = _columns()
    if "product_name" not in columns:
        op.add_column("order_items", sa.Column("product_name", sa.String(length=120), nullable=True))

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE order_items
            SET product_name = COALESCE(
                (SELECT products.name FROM products WHERE products.id = order_items.product_id),
                '历史商品'
            )
            WHERE product_name IS NULL OR product_name = ''
            """
        )
    )

    columns = _columns()
    if columns["product_name"].get("nullable", True):
        with op.batch_alter_table("order_items") as batch_op:
            batch_op.alter_column(
                "product_name",
                existing_type=sa.String(length=120),
                nullable=False,
            )


def downgrade() -> None:
    if "product_name" in _columns():
        with op.batch_alter_table("order_items") as batch_op:
            batch_op.drop_column("product_name")
