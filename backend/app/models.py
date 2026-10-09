from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """SQLite 使用无时区字段，统一保存去掉 tzinfo 的 UTC 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


class School(Base):
    __tablename__ = "schools"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    authorization_status: Mapped[str] = mapped_column(String(32), default="unverified", nullable=False)

    delivery_points: Mapped[list[DeliveryPoint]] = relationship(back_populates="school")


class DeliveryPoint(Base):
    __tablename__ = "delivery_points"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="unverified", nullable=False)

    school: Mapped[School] = relationship(back_populates="delivery_points")


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    zone: Mapped[str] = mapped_column(String(80), nullable=False)
    address: Mapped[str] = mapped_column(String(200), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="demo", nullable=False)

    products: Mapped[list[Product]] = relationship(back_populates="merchant")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    merchant: Mapped[Merchant] = relationship(back_populates="products")


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    depart_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    delivery_start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    delivery_end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False, index=True)
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("2.50"), nullable=False)
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.0800"), nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), nullable=False, index=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False, index=True)
    delivery_point_id: Mapped[str] = mapped_column(ForeignKey("delivery_points.id"), nullable=False)
    student_alias: Mapped[str] = mapped_column(String(80), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    mock_paid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    items: Mapped[list[OrderItem]] = relationship(back_populates="order", cascade="all, delete-orphan")
    parcels: Mapped[list[Parcel]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class Parcel(Base):
    __tablename__ = "parcels"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)

    order: Mapped[Order] = relationship(back_populates="parcels")


class PickupRoute(Base):
    __tablename__ = "pickup_routes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    stops: Mapped[list[PickupStop]] = relationship(
        back_populates="route", order_by="PickupStop.sequence", cascade="all, delete-orphan"
    )


class PickupStop(Base):
    __tablename__ = "pickup_stops"
    __table_args__ = (
        UniqueConstraint("route_id", "sequence", name="uq_pickup_stop_sequence"),
        UniqueConstraint("route_id", "merchant_id", name="uq_pickup_stop_merchant"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    route_id: Mapped[str] = mapped_column(ForeignKey("pickup_routes.id", ondelete="CASCADE"), nullable=False)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_pickup_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    route: Mapped[PickupRoute] = relationship(back_populates="stops")
    handoff: Mapped[PickupHandoff | None] = relationship(back_populates="stop", uselist=False)


class PickupHandoff(Base):
    __tablename__ = "pickup_handoffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stop_id: Mapped[str] = mapped_column(ForeignKey("pickup_stops.id"), nullable=False, unique=True)
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    planned_count: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    stop: Mapped[PickupStop] = relationship(back_populates="handoff")
    parcels: Mapped[list[PickupHandoffParcel]] = relationship(
        back_populates="handoff", cascade="all, delete-orphan"
    )


class PickupHandoffParcel(Base):
    __tablename__ = "pickup_handoff_parcels"
    __table_args__ = (UniqueConstraint("handoff_id", "parcel_id", name="uq_handoff_parcel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    handoff_id: Mapped[int] = mapped_column(ForeignKey("pickup_handoffs.id", ondelete="CASCADE"), nullable=False)
    parcel_id: Mapped[str] = mapped_column(ForeignKey("parcels.id"), nullable=False, unique=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)

    handoff: Mapped[PickupHandoff] = relationship(back_populates="parcels")


class DeliveryTask(Base):
    __tablename__ = "delivery_tasks"
    __table_args__ = (UniqueConstraint("batch_id", "delivery_point_id", name="uq_delivery_task_point"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), nullable=False)
    delivery_point_id: Mapped[str] = mapped_column(ForeignKey("delivery_points.id"), nullable=False)
    assigned_actor: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="assigned", nullable=False)

    parcels: Mapped[list[DeliveryTaskParcel]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class DeliveryTaskParcel(Base):
    __tablename__ = "delivery_task_parcels"
    __table_args__ = (UniqueConstraint("task_id", "parcel_id", name="uq_delivery_task_parcel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("delivery_tasks.id", ondelete="CASCADE"), nullable=False)
    parcel_id: Mapped[str] = mapped_column(ForeignKey("parcels.id"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), default="assigned", nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    delivered_by: Mapped[str | None] = mapped_column(String(80))

    task: Mapped[DeliveryTask] = relationship(back_populates="parcels")


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), nullable=False, index=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    parcel_id: Mapped[str] = mapped_column(ForeignKey("parcels.id"), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False, index=True)
    resolution: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_by: Mapped[str | None] = mapped_column(String(80))


class CostRecord(Base):
    __tablename__ = "cost_records"
    __table_args__ = (UniqueConstraint("batch_id", "category", name="uq_cost_category"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    note: Mapped[str] = mapped_column(String(200), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id"), index=True)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("key", "action", name="uq_idempotency_key_action"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
