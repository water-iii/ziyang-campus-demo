from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import ceil
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .auth import DemoActor
from .errors import BusinessError
from .models import (
    AuditLog,
    Batch,
    CostRecord,
    DemoClock,
    DeliveryPoint,
    DeliveryTask,
    DeliveryTaskParcel,
    IdempotencyRecord,
    Issue,
    Merchant,
    Order,
    OrderItem,
    Parcel,
    PickupHandoff,
    PickupHandoffParcel,
    PickupEarlyCloseAuthorization,
    PickupRoute,
    PickupStop,
    Product,
)
from .schemas import HandoffCreate, OrderCreate


BATCH_STATUSES = ("open", "cutoff", "collecting", "transit", "campus", "delivering", "finished")
PARCEL_PROGRESS = {"pending": 0, "ready": 1, "picked": 2, "campus": 3, "out": 4, "delivered": 5}
DEPARTURE_LOADING_BUFFER_MINUTES = 5


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def normalized_time(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def demo_time_control_enabled(db: Session) -> bool:
    return db.info.get("app_env") in {"demo", "test"}


def require_demo_time_control(db: Session) -> None:
    require(demo_time_control_enabled(db), "当前运行环境未启用演示时间控制。", 404)


def business_now(db: Session) -> datetime:
    if demo_time_control_enabled(db):
        clock = db.get(DemoClock, "default")
        if clock is not None and clock.frozen_at is not None:
            return clock.frozen_at
    return now()


def unique_id(prefix: str) -> str:
    """生成不依赖“最大编号 + 1”的并发安全公开标识。"""
    return f"{prefix}{uuid4().hex[:24]}"


def require(condition: bool, message: str, status_code: int = 409) -> None:
    if not condition:
        raise BusinessError(message, status_code)


def get_batch(db: Session, batch_id: str) -> Batch:
    batch = db.get(Batch, batch_id)
    require(batch is not None, "班次不存在。", 404)
    return batch


def audit(
    db: Session,
    actor: DemoActor,
    action: str,
    entity_type: str,
    entity_id: str,
    *,
    batch_id: str | None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            batch_id=batch_id,
            actor_role=actor.role,
            actor_id=actor.actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )
    )


def demo_clock_status(db: Session) -> dict[str, Any]:
    require_demo_time_control(db)
    clock = db.get(DemoClock, "default")
    current = business_now(db)
    return {
        "environment": db.info.get("app_env"),
        "current_at": current.isoformat(),
        "frozen_at": clock.frozen_at.isoformat() if clock and clock.frozen_at else None,
        "simulated": bool(clock and clock.frozen_at),
    }


def set_demo_clock(db: Session, current_at: datetime, actor: DemoActor) -> dict[str, Any]:
    require_demo_time_control(db)
    frozen_at = normalized_time(current_at)
    clock = db.get(DemoClock, "default")
    if clock is None:
        clock = DemoClock(id="default")
        db.add(clock)
    clock.frozen_at = frozen_at
    clock.updated_by = actor.actor_id
    audit(
        db,
        actor,
        "demo.clock.set",
        "demo_clock",
        clock.id,
        batch_id=None,
        details={"current_at": frozen_at.isoformat(), "environment": db.info.get("app_env")},
    )
    return {
        "environment": db.info.get("app_env"),
        "current_at": frozen_at.isoformat(),
        "frozen_at": frozen_at.isoformat(),
        "simulated": True,
    }


def reset_demo_clock(db: Session, actor: DemoActor) -> dict[str, Any]:
    require_demo_time_control(db)
    clock = db.get(DemoClock, "default")
    if clock is None:
        clock = DemoClock(id="default")
        db.add(clock)
    clock.frozen_at = None
    clock.updated_by = actor.actor_id
    audit(
        db,
        actor,
        "demo.clock.reset",
        "demo_clock",
        clock.id,
        batch_id=None,
        details={"environment": db.info.get("app_env")},
    )
    current = now()
    return {
        "environment": db.info.get("app_env"),
        "current_at": current.isoformat(),
        "frozen_at": None,
        "simulated": False,
    }


def execute_idempotent(
    db: Session,
    key: str | None,
    action: str,
    operation: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    if key:
        require(len(key) <= 120, "Idempotency-Key 不能超过120个字符。", 422)
        existing = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == key))
        if existing:
            require(existing.action == action, "同一个 Idempotency-Key 不能用于不同操作。")
            return {**existing.response_json, "idempotent_replay": True}
    result = operation()
    if key:
        db.add(IdempotencyRecord(key=key, action=action, response_json=result))
        db.flush()
    return {**result, "idempotent_replay": False}


def order_status(order: Order, batch_status: str) -> str:
    parcel_states = [parcel.status for parcel in order.parcels]
    if any(state in {"missing", "pickup_timeout", "pickup_abandoned"} for state in parcel_states):
        return "pickup_exception"
    if parcel_states and all(state == "refunded" for state in parcel_states):
        return "refunded"
    if any(state == "refunded" for state in parcel_states):
        if all(state in {"refunded", "delivered"} for state in parcel_states):
            return "partially_refunded_completed"
        return "partial_exception"
    if order.accepted_at is None:
        return "awaiting_merchant_acceptance"
    minimum = min((PARCEL_PROGRESS.get(state, 0) for state in parcel_states), default=0)
    if minimum == 0:
        return "preparing"
    if minimum == 1:
        return "ready_for_pickup"
    if minimum == 2:
        return "in_transit" if batch_status in {"transit", "campus", "delivering", "finished"} else "loaded"
    if minimum == 3:
        return "at_campus"
    if minimum == 4:
        return "out_for_delivery"
    return "delivered"


def serialize_order(order: Order, batch_status: str) -> dict[str, Any]:
    return {
        "id": order.id,
        "batch_id": order.batch_id,
        "merchant_id": order.merchant_id,
        "delivery_point_id": order.delivery_point_id,
        "student_alias": order.student_alias,
        "amount": float(order.amount),
        "accepted_at": order.accepted_at.isoformat() if order.accepted_at else None,
        "created_at": order.created_at.isoformat(),
        "mock_paid": order.mock_paid,
        "status": order_status(order, batch_status),
        "items": [
            {
                "product_id": item.product_id,
                "name": item.product_name,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
            }
            for item in order.items
        ],
        "parcels": [{"id": parcel.id, "status": parcel.status} for parcel in order.parcels],
    }


def list_orders(db: Session, batch_id: str, merchant_id: str | None = None) -> list[dict[str, Any]]:
    batch = get_batch(db, batch_id)
    query = (
        select(Order)
        .where(Order.batch_id == batch_id)
        .options(selectinload(Order.items), selectinload(Order.parcels))
        .order_by(Order.id)
    )
    if merchant_id:
        query = query.where(Order.merchant_id == merchant_id)
    return [serialize_order(order, batch.status) for order in db.scalars(query).unique().all()]


def get_order_detail(db: Session, order_id: str) -> dict[str, Any]:
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items), selectinload(Order.parcels))
    )
    require(order is not None, "订单不存在。", 404)
    batch = get_batch(db, order.batch_id)
    return serialize_order(order, batch.status)


def create_order(db: Session, payload: OrderCreate, actor: DemoActor) -> dict[str, Any]:
    batch = get_batch(db, payload.batch_id)
    require(batch.status == "open", "本班已截单，无法新增演示订单。")
    current_count = int(
        db.scalar(select(func.count()).select_from(Order).where(Order.batch_id == payload.batch_id)) or 0
    )
    require(current_count < batch.capacity, "本班已达到演示容量上限。")
    merchant = db.get(Merchant, payload.merchant_id)
    require(merchant is not None and merchant.status == "demo", "演示商家不存在。", 404)
    point = db.get(DeliveryPoint, payload.delivery_point_id)
    require(point is not None and point.school_id == batch.school_id, "请选择本校预先配置的演示交接点。", 422)

    product_ids = [item.product_id for item in payload.items]
    require(len(product_ids) == len(set(product_ids)), "同一商品请合并为一条明细。", 422)
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_(product_ids))).all()
    }
    require(len(products) == len(product_ids), "订单包含不存在的商品。", 422)
    require(
        all(product.merchant_id == payload.merchant_id and product.active for product in products.values()),
        "一张订单只能包含同一演示商家的有效商品。",
        422,
    )

    order_id = unique_id("O")
    amount = sum((products[item.product_id].price * item.quantity for item in payload.items), Decimal("0"))
    order = Order(
        id=order_id,
        batch_id=batch.id,
        merchant_id=payload.merchant_id,
        delivery_point_id=payload.delivery_point_id,
        student_alias=payload.student_alias,
        amount=amount,
        mock_paid=True,
    )
    for item in payload.items:
        order.items.append(
            OrderItem(
                product_id=item.product_id,
                product_name=products[item.product_id].name,
                quantity=item.quantity,
                unit_price=products[item.product_id].price,
            )
        )
    bag_count = max(1, ceil(sum(item.quantity for item in payload.items) / 2))
    for index in range(1, bag_count + 1):
        order.parcels.append(
            Parcel(id=f"P{order_id[1:]}-{index}", merchant_id=payload.merchant_id, status="pending")
        )
    db.add(order)
    audit(
        db,
        actor,
        "order.create",
        "order",
        order.id,
        batch_id=batch.id,
        details={"merchant_id": payload.merchant_id, "parcels": bag_count, "mock_payment": True},
    )
    db.flush()
    refreshed = db.scalar(
        select(Order)
        .where(Order.id == order.id)
        .options(selectinload(Order.items), selectinload(Order.parcels))
    )
    return {"order": serialize_order(refreshed, batch.status)}


def cutoff_batch(db: Session, batch_id: str, actor: DemoActor) -> dict[str, Any]:
    batch = get_batch(db, batch_id)
    require(batch.status == "open", "只有开放预订的班次可以截单。")
    batch.status = "cutoff"
    count = int(db.scalar(select(func.count()).select_from(Order).where(Order.batch_id == batch_id)) or 0)
    audit(db, actor, "batch.cutoff", "batch", batch.id, batch_id=batch.id, details={"orders": count})
    return {"batch_id": batch.id, "status": batch.status, "orders": count}


def accept_merchant_orders(db: Session, batch_id: str, merchant_id: str, actor: DemoActor) -> dict[str, Any]:
    batch = get_batch(db, batch_id)
    require(batch.status in {"cutoff", "collecting"}, "请先截单，再确认商家出餐。")
    orders = db.scalars(
        select(Order).where(Order.batch_id == batch_id, Order.merchant_id == merchant_id).order_by(Order.id)
    ).all()
    require(bool(orders), "商家暂无订单。", 404)
    pending_orders = [order for order in orders if order.accepted_at is None]
    require(bool(pending_orders), "该商家订单已经确认，不能重复接单。")
    accepted_at = now()
    for order in pending_orders:
        order.accepted_at = accepted_at
    audit(
        db,
        actor,
        "merchant.accept_orders",
        "merchant",
        merchant_id,
        batch_id=batch.id,
        details={"orders": len(pending_orders), "mode": "bulk"},
    )
    return {"batch_id": batch.id, "merchant_id": merchant_id, "accepted_orders": len(pending_orders)}


def accept_order(db: Session, order_id: str, actor: DemoActor) -> dict[str, Any]:
    order = db.get(Order, order_id)
    require(order is not None, "订单不存在。", 404)
    batch = get_batch(db, order.batch_id)
    require(batch.status in {"cutoff", "collecting"}, "请先截单，再确认商家订单。")
    require(order.accepted_at is None, "该订单已经确认，不能重复接单。")
    order.accepted_at = now()
    audit(
        db,
        actor,
        "merchant.accept_order",
        "order",
        order.id,
        batch_id=batch.id,
        details={"merchant_id": order.merchant_id, "mode": "single"},
    )
    return {"batch_id": batch.id, "merchant_id": order.merchant_id, "order_id": order.id, "accepted": True}


def pack_merchant(db: Session, batch_id: str, merchant_id: str, actor: DemoActor) -> dict[str, Any]:
    batch = get_batch(db, batch_id)
    require(batch.status in {"cutoff", "collecting"}, "当前班次不能进行打包操作。")
    orders = db.scalars(select(Order).where(Order.batch_id == batch_id, Order.merchant_id == merchant_id)).all()
    require(bool(orders), "商家暂无订单。", 404)
    require(all(order.accepted_at is not None for order in orders), "请先确认该商家的全部订单。")
    stop = db.scalar(
        select(PickupStop)
        .join(PickupRoute)
        .where(PickupRoute.batch_id == batch_id, PickupStop.merchant_id == merchant_id)
        .options(selectinload(PickupStop.handoff))
    )
    require(stop is not None, "取货线路中不存在该商家。", 404)
    require(stop.handoff is None, "该商家已发生取货交接，不能重新打包。")
    parcels = db.scalars(
        select(Parcel)
        .join(Order)
        .where(Order.batch_id == batch_id, Parcel.merchant_id == merchant_id)
    ).all()
    pending = [parcel for parcel in parcels if parcel.status == "pending"]
    require(bool(pending), "本店没有待打包餐袋，不能重复打包。")
    require(all(parcel.status in {"pending", "ready"} for parcel in parcels), "本店已发生履约流转，不能批量打包。")
    for parcel in pending:
        parcel.status = "ready"
    audit(
        db,
        actor,
        "merchant.pack",
        "merchant",
        merchant_id,
        batch_id=batch.id,
        details={"parcels": len(pending), "mode": "bulk"},
    )
    return {"batch_id": batch.id, "merchant_id": merchant_id, "packed_parcels": len(pending)}


def pack_parcel(db: Session, parcel_id: str, actor: DemoActor) -> dict[str, Any]:
    parcel = db.get(Parcel, parcel_id)
    require(parcel is not None, "餐袋不存在。", 404)
    order = db.get(Order, parcel.order_id)
    require(order is not None, "餐袋关联订单不存在。", 404)
    batch = get_batch(db, order.batch_id)
    require(batch.status in {"cutoff", "collecting"}, "当前班次不能进行打包操作。")
    require(order.accepted_at is not None, "请先确认该餐袋所属订单。")
    require(parcel.status == "pending", "该餐袋已经打包或进入后续履约，不能重复打包。")
    parcel.status = "ready"
    audit(
        db,
        actor,
        "merchant.pack_parcel",
        "parcel",
        parcel.id,
        batch_id=batch.id,
        details={"merchant_id": parcel.merchant_id, "order_id": order.id, "mode": "single"},
    )
    return {
        "batch_id": batch.id,
        "merchant_id": parcel.merchant_id,
        "order_id": order.id,
        "parcel_id": parcel.id,
        "parcel_status": parcel.status,
    }


def validate_stop_timing(stop: PickupStop, batch: Batch) -> None:
    require(stop.planned_pickup_at <= stop.latest_handoff_at, "站点最晚交接时间不能早于预计到店时间。")
    latest_departure_safe_time = batch.depart_at - timedelta(minutes=DEPARTURE_LOADING_BUFFER_MINUTES)
    require(
        stop.latest_handoff_at <= latest_departure_safe_time,
        f"站点最晚交接时间必须至少早于计划发车 {DEPARTURE_LOADING_BUFFER_MINUTES} 分钟。",
    )


def authorize_pickup_early_close(
    db: Session,
    stop_id: str,
    reason: str,
    actor: DemoActor,
) -> dict[str, Any]:
    stop = db.scalar(
        select(PickupStop)
        .where(PickupStop.id == stop_id)
        .options(
            selectinload(PickupStop.handoff),
            selectinload(PickupStop.early_close_authorization),
            selectinload(PickupStop.route),
        )
    )
    require(stop is not None, "取货站点不存在。", 404)
    batch = get_batch(db, stop.route.batch_id)
    validate_stop_timing(stop, batch)
    require(batch.status in {"cutoff", "collecting"}, "当前班次不能授权提前关闭交接。")
    require(stop.handoff is None, "该站点已经完成交接，无需提前关闭授权。")
    require(stop.early_close_authorization is None, "该站点已经取得提前关闭授权。")
    current_time = business_now(db)
    require(current_time < stop.latest_handoff_at, "已到站点最晚交接时间，无需提前关闭授权。")

    parcels = db.scalars(
        select(Parcel)
        .join(Order)
        .where(Order.batch_id == batch.id, Parcel.merchant_id == stop.merchant_id)
        .options(selectinload(Parcel.order))
    ).all()
    require(bool(parcels), "商家没有餐袋。", 404)
    require(
        all(parcel.order.accepted_at is not None for parcel in parcels),
        "商家仍有未接单订单，不能授权司机绕过接单校验。",
    )
    pending_ids = sorted(parcel.id for parcel in parcels if parcel.status == "pending")
    require(bool(pending_ids), "该站点没有制作中的餐袋，无需提前关闭授权。")
    require(
        all(parcel.status in {"pending", "ready"} for parcel in parcels),
        "该站点餐袋已进入其他履约状态，不能授权提前关闭。",
    )

    authorization = PickupEarlyCloseAuthorization(
        id=unique_id("EA"),
        stop_id=stop.id,
        authorized_by=actor.actor_id,
        reason=reason,
        business_time=current_time,
    )
    db.add(authorization)
    audit(
        db,
        actor,
        "pickup.early_close_authorize",
        "pickup_stop",
        stop.id,
        batch_id=batch.id,
        details={
            "authorization_id": authorization.id,
            "merchant_id": stop.merchant_id,
            "reason": reason,
            "pending_parcel_ids": pending_ids,
            "business_time": current_time.isoformat(),
            "latest_handoff_at": stop.latest_handoff_at.isoformat(),
        },
    )
    return {
        "authorization_id": authorization.id,
        "stop_id": stop.id,
        "merchant_id": stop.merchant_id,
        "reason": reason,
        "pending_parcel_ids": pending_ids,
        "business_time": current_time.isoformat(),
        "latest_handoff_at": stop.latest_handoff_at.isoformat(),
    }


def pickup_handoff(
    db: Session,
    stop_id: str,
    payload: HandoffCreate,
    actor: DemoActor,
) -> dict[str, Any]:
    stop = db.scalar(
        select(PickupStop)
        .where(PickupStop.id == stop_id)
        .options(
            selectinload(PickupStop.handoff),
            selectinload(PickupStop.early_close_authorization),
            selectinload(PickupStop.route).selectinload(PickupRoute.stops),
        )
    )
    require(stop is not None, "取货站点不存在。", 404)
    batch = get_batch(db, stop.route.batch_id)
    validate_stop_timing(stop, batch)
    require(batch.status in {"cutoff", "collecting"}, "当前班次不允许取货。")
    require(stop.handoff is None, "该站点已确认过交接，不能重复交接。")

    previous_stops = [item for item in stop.route.stops if item.sequence < stop.sequence]
    if previous_stops:
        done_ids = set(db.scalars(select(PickupHandoff.stop_id).where(PickupHandoff.stop_id.in_([s.id for s in previous_stops]))).all())
        require(all(item.id in done_ids for item in previous_stops), "请先完成上一站取货。")

    parcels = db.scalars(
        select(Parcel)
        .join(Order)
        .where(Order.batch_id == batch.id, Parcel.merchant_id == stop.merchant_id)
        .options(selectinload(Parcel.order))
        .order_by(Parcel.id)
    ).all()
    require(bool(parcels), "商家没有餐袋。", 404)
    require(
        all(parcel.order.accepted_at is not None for parcel in parcels),
        "该商家仍有未接单订单，司机不能绕过接单校验。",
    )
    require(
        all(parcel.status in {"pending", "ready"} for parcel in parcels),
        "该商家餐袋已进入其他履约状态，不能再次交接。",
    )
    planned_count = len(parcels)
    unready_ids = {parcel.id for parcel in parcels if parcel.status == "pending"}
    current_time = business_now(db)
    deadline_reached = current_time >= stop.latest_handoff_at
    early_close_authorization = stop.early_close_authorization
    if unready_ids:
        require(
            deadline_reached or early_close_authorization is not None,
            (
                f"该商家存在未打包餐袋；站点最晚交接时间 {stop.latest_handoff_at.isoformat()} 前，"
                "必须取得运营提前关闭授权。"
            ),
        )
    require(payload.actual_count <= planned_count, "实际餐袋数不能超过本次计划数。", 422)
    parcel_by_id = {parcel.id: parcel for parcel in parcels}
    missing_ids = set(payload.missing_parcel_ids)
    require(missing_ids.issubset(parcel_by_id), "缺袋编号不属于当前商家或当前班次。", 422)
    if payload.picked_parcel_ids is None:
        picked_ids = set(parcel_by_id) - missing_ids
    else:
        picked_ids = set(payload.picked_parcel_ids)
        require(picked_ids.issubset(parcel_by_id), "实装餐袋编号不属于当前商家或当前班次。", 422)
        require(picked_ids | missing_ids == set(parcel_by_id), "必须逐袋明确实装或缺袋结果。", 422)
    require(
        all(parcel_by_id[parcel_id].status == "ready" for parcel_id in picked_ids),
        "只有已接单且已打包的餐袋可以确认实装。",
    )
    require(len(picked_ids) == payload.actual_count, "实际数量必须与实装餐袋编号数量一致。", 422)
    shortage_count = planned_count - payload.actual_count
    require(len(missing_ids) == shortage_count, "缺袋编号数量必须等于计划数与实际数之差。", 422)

    timeout_ids: set[str] = set()
    abandoned_ids: set[str] = set()
    shortage_ids: set[str] = set()
    handoff_outcomes: dict[str, str] = {}
    for parcel in parcels:
        if parcel.id in missing_ids:
            if parcel.status == "pending":
                if deadline_reached:
                    parcel.status = "pickup_timeout"
                    issue_type = "merchant_preparation_timeout"
                    outcome = "pickup_timeout"
                    timeout_ids.add(parcel.id)
                else:
                    parcel.status = "pickup_abandoned"
                    issue_type = "merchant_preparation_early_close"
                    outcome = "pickup_abandoned"
                    abandoned_ids.add(parcel.id)
            else:
                parcel.status = "missing"
                issue_type = "merchant_handoff_shortage"
                outcome = "missing"
                shortage_ids.add(parcel.id)
            issue_id = unique_id("EX")
            db.add(
                Issue(
                    id=issue_id,
                    batch_id=batch.id,
                    merchant_id=stop.merchant_id,
                    order_id=parcel.order_id,
                    parcel_id=parcel.id,
                    type=issue_type,
                    status="open",
                )
            )
            audit(
                db,
                actor,
                "issue.open",
                "issue",
                issue_id,
                batch_id=batch.id,
                details={
                    "merchant_id": stop.merchant_id,
                    "parcel_id": parcel.id,
                    "order_id": parcel.order_id,
                    "type": issue_type,
                },
            )
            handoff_outcomes[parcel.id] = outcome
        elif parcel.id in picked_ids:
            parcel.status = "picked"
            handoff_outcomes[parcel.id] = "picked"

    handoff = PickupHandoff(
        stop_id=stop.id,
        actor=actor.actor_id,
        planned_count=planned_count,
        actual_count=payload.actual_count,
    )
    db.add(handoff)
    db.flush()
    for parcel in parcels:
        db.add(
            PickupHandoffParcel(
                handoff_id=handoff.id,
                parcel_id=parcel.id,
                outcome=handoff_outcomes[parcel.id],
            )
        )
    batch.status = "collecting"
    audit(
        db,
        actor,
        "pickup.handoff",
        "pickup_stop",
        stop.id,
        batch_id=batch.id,
        details={
            "merchant_id": stop.merchant_id,
            "planned_count": planned_count,
            "actual_count": payload.actual_count,
            "picked_parcel_ids": sorted(picked_ids),
            "missing_parcel_ids": sorted(missing_ids),
            "shortage_parcel_ids": sorted(shortage_ids),
            "timeout_parcel_ids": sorted(timeout_ids),
            "abandoned_parcel_ids": sorted(abandoned_ids),
            "business_time": current_time.isoformat(),
            "latest_handoff_at": stop.latest_handoff_at.isoformat(),
            "deadline_reached": deadline_reached,
            "early_close_authorization_id": (
                early_close_authorization.id if early_close_authorization and not deadline_reached else None
            ),
        },
    )
    return {
        "batch_id": batch.id,
        "stop_id": stop.id,
        "merchant_id": stop.merchant_id,
        "planned_count": planned_count,
        "actual_count": payload.actual_count,
        "picked_parcel_ids": sorted(picked_ids),
        "missing_parcel_ids": sorted(missing_ids),
        "shortage_parcel_ids": sorted(shortage_ids),
        "timeout_parcel_ids": sorted(timeout_ids),
        "abandoned_parcel_ids": sorted(abandoned_ids),
        "business_time": current_time.isoformat(),
        "latest_handoff_at": stop.latest_handoff_at.isoformat(),
        "deadline_reached": deadline_reached,
        "early_close_authorization_id": (
            early_close_authorization.id if early_close_authorization and not deadline_reached else None
        ),
    }


def depart_batch(db: Session, batch_id: str, actor: DemoActor) -> dict[str, Any]:
    batch = get_batch(db, batch_id)
    require(batch.status == "collecting", "请先完成城区取货。")
    stops = db.scalars(
        select(PickupStop).join(PickupRoute).where(PickupRoute.batch_id == batch_id).order_by(PickupStop.sequence)
    ).all()
    handoff_count = int(
        db.scalar(select(func.count()).select_from(PickupHandoff).where(PickupHandoff.stop_id.in_([stop.id for stop in stops])))
        or 0
    )
    require(bool(stops) and handoff_count == len(stops), "还有商家未完成交接，不能发车。")
    loaded = int(
        db.scalar(
            select(func.count())
            .select_from(Parcel)
            .join(Order)
            .where(Order.batch_id == batch_id, Parcel.status == "picked")
        )
        or 0
    )
    require(loaded > 0, "未装载任何餐袋，不能确认发车。")
    batch.status = "transit"
    audit(db, actor, "batch.depart", "batch", batch.id, batch_id=batch.id, details={"loaded_parcels": loaded})
    return {"batch_id": batch.id, "status": batch.status, "loaded_parcels": loaded}


def campus_receive(db: Session, batch_id: str, actor: DemoActor) -> dict[str, Any]:
    batch = get_batch(db, batch_id)
    require(batch.status == "transit", "请先确认车辆发车。")
    parcels = db.scalars(select(Parcel).join(Order).where(Order.batch_id == batch_id, Parcel.status == "picked")).all()
    require(bool(parcels), "当前无可接收的餐袋。")
    for parcel in parcels:
        parcel.status = "campus"
    batch.status = "campus"
    audit(db, actor, "campus.receive", "batch", batch.id, batch_id=batch.id, details={"parcels": len(parcels)})
    return {"batch_id": batch.id, "status": batch.status, "received_parcels": len(parcels)}


def assign_delivery(db: Session, batch_id: str, actor: DemoActor) -> dict[str, Any]:
    batch = get_batch(db, batch_id)
    require(batch.status == "campus", "请先完成到校清点交接。")
    parcels = db.scalars(
        select(Parcel)
        .join(Order)
        .where(Order.batch_id == batch_id, Parcel.status == "campus")
        .options(selectinload(Parcel.order))
    ).all()
    require(bool(parcels), "没有可分派餐袋。")
    point_ids = sorted({parcel.order.delivery_point_id for parcel in parcels})
    for point_id in point_ids:
        task = DeliveryTask(
            batch_id=batch.id,
            delivery_point_id=point_id,
            assigned_actor=actor.actor_id,
            status="assigned",
        )
        db.add(task)
        db.flush()
        for parcel in parcels:
            if parcel.order.delivery_point_id == point_id:
                db.add(DeliveryTaskParcel(task_id=task.id, parcel_id=parcel.id, status="assigned"))
    for parcel in parcels:
        parcel.status = "out"
    batch.status = "delivering"
    audit(
        db,
        actor,
        "delivery.assign",
        "batch",
        batch.id,
        batch_id=batch.id,
        details={"parcels": len(parcels), "tasks": len(point_ids)},
    )
    return {"batch_id": batch.id, "status": batch.status, "assigned_parcels": len(parcels), "tasks": len(point_ids)}


def update_finished(db: Session, batch: Batch, actor: DemoActor) -> bool:
    if batch.status not in {"delivering", "finished"}:
        return False
    # Session 关闭了 autoflush；结案判断必须看到本事务刚完成的餐袋/异常状态。
    db.flush()
    unfinished = int(
        db.scalar(
            select(func.count())
            .select_from(Parcel)
            .join(Order)
            .where(Order.batch_id == batch.id, Parcel.status.not_in({"delivered", "refunded"}))
        )
        or 0
    )
    open_issues = int(
        db.scalar(select(func.count()).select_from(Issue).where(Issue.batch_id == batch.id, Issue.status == "open"))
        or 0
    )
    if unfinished == 0 and open_issues == 0 and batch.status != "finished":
        batch.status = "finished"
        audit(db, actor, "batch.finish", "batch", batch.id, batch_id=batch.id, details={})
        return True
    return False


def complete_delivery(db: Session, batch_id: str, actor: DemoActor) -> dict[str, Any]:
    batch = get_batch(db, batch_id)
    require(batch.status == "delivering", "请先分配配送任务。")
    parcels = db.scalars(select(Parcel).join(Order).where(Order.batch_id == batch_id, Parcel.status == "out")).all()
    require(bool(parcels), "没有待交付餐袋。")
    for parcel in parcels:
        parcel.status = "delivered"
    tasks = db.scalars(select(DeliveryTask).where(DeliveryTask.batch_id == batch_id)).all()
    for task in tasks:
        task.status = "completed"
    task_parcels = db.scalars(
        select(DeliveryTaskParcel).join(DeliveryTask).where(DeliveryTask.batch_id == batch_id)
    ).all()
    delivered_at = now()
    for link in task_parcels:
        link.status = "delivered"
        link.delivered_at = delivered_at
        link.delivered_by = actor.actor_id
    audit(
        db,
        actor,
        "delivery.complete",
        "batch",
        batch.id,
        batch_id=batch.id,
        details={"parcels": len(parcels)},
    )
    finished = update_finished(db, batch, actor)
    return {"batch_id": batch.id, "status": batch.status, "delivered_parcels": len(parcels), "finished": finished}


def list_delivery_tasks(db: Session, batch_id: str) -> list[dict[str, Any]]:
    get_batch(db, batch_id)
    tasks = db.scalars(
        select(DeliveryTask)
        .where(DeliveryTask.batch_id == batch_id)
        .options(selectinload(DeliveryTask.parcels))
        .order_by(DeliveryTask.id)
    ).unique().all()
    parcel_ids = [link.parcel_id for task in tasks for link in task.parcels]
    parcel_map: dict[str, Parcel] = {}
    order_map: dict[str, Order] = {}
    if parcel_ids:
        parcel_map = {parcel.id: parcel for parcel in db.scalars(select(Parcel).where(Parcel.id.in_(parcel_ids))).all()}
        order_ids = {parcel.order_id for parcel in parcel_map.values()}
        order_map = {order.id: order for order in db.scalars(select(Order).where(Order.id.in_(order_ids))).all()}
    return [
        {
            "id": task.id,
            "batch_id": task.batch_id,
            "delivery_point_id": task.delivery_point_id,
            "assigned_actor": task.assigned_actor,
            "status": task.status,
            "parcels": [
                {
                    "parcel_id": link.parcel_id,
                    "order_id": order_map[parcel_map[link.parcel_id].order_id].id,
                    "parcel_status": parcel_map[link.parcel_id].status,
                    "task_status": link.status,
                    "delivered_at": link.delivered_at.isoformat() if link.delivered_at else None,
                }
                for link in task.parcels
            ],
        }
        for task in tasks
    ]


def deliver_task_parcel(db: Session, task_id: int, parcel_id: str, actor: DemoActor) -> dict[str, Any]:
    task = db.get(DeliveryTask, task_id)
    require(task is not None, "配送任务不存在。", 404)
    batch = get_batch(db, task.batch_id)
    require(batch.status == "delivering", "当前班次不能确认逐袋交付。")
    link = db.scalar(
        select(DeliveryTaskParcel).where(
            DeliveryTaskParcel.task_id == task_id,
            DeliveryTaskParcel.parcel_id == parcel_id,
        )
    )
    require(link is not None, "该餐袋不属于此配送任务。", 404)
    require(link.status == "assigned", "该餐袋已经确认交付，不能重复操作。")
    parcel = db.get(Parcel, parcel_id)
    require(parcel is not None and parcel.status == "out", "餐袋当前不处于末端配送状态。")
    parcel.status = "delivered"
    link.status = "delivered"
    link.delivered_at = now()
    link.delivered_by = actor.actor_id
    db.flush()
    remaining = int(
        db.scalar(
            select(func.count())
            .select_from(DeliveryTaskParcel)
            .where(DeliveryTaskParcel.task_id == task_id, DeliveryTaskParcel.status != "delivered")
        )
        or 0
    )
    if remaining == 0:
        task.status = "completed"
    audit(
        db,
        actor,
        "delivery.deliver_parcel",
        "parcel",
        parcel.id,
        batch_id=batch.id,
        details={"task_id": task.id, "order_id": parcel.order_id, "mode": "single"},
    )
    finished = update_finished(db, batch, actor)
    return {
        "batch_id": batch.id,
        "batch_status": batch.status,
        "task_id": task.id,
        "task_status": task.status,
        "parcel_id": parcel.id,
        "parcel_status": parcel.status,
        "finished": finished,
    }


def resolve_issue(db: Session, issue_id: str, resolution: str, actor: DemoActor) -> dict[str, Any]:
    issue = db.get(Issue, issue_id)
    require(issue is not None, "异常不存在。", 404)
    require(issue.status == "open", "异常已经处理，不能重复模拟退款。")
    parcel = db.get(Parcel, issue.parcel_id)
    require(
        parcel is not None and parcel.status in {"missing", "pickup_timeout", "pickup_abandoned"},
        "此异常没有可处理的未装车餐袋。",
    )
    parcel.status = "refunded"
    issue.status = "resolved"
    issue.resolution = resolution
    issue.resolved_at = now()
    issue.resolved_by = actor.actor_id
    audit(
        db,
        actor,
        "issue.resolve",
        "issue",
        issue.id,
        batch_id=issue.batch_id,
        details={"parcel_id": parcel.id, "resolution": resolution, "real_payment_action": False},
    )
    batch = get_batch(db, issue.batch_id)
    finished = update_finished(db, batch, actor)
    return {
        "issue_id": issue.id,
        "status": issue.status,
        "parcel_status": parcel.status,
        "batch_status": batch.status,
        "finished": finished,
        "real_payment_action": False,
    }


def update_fixed_cost(db: Session, batch_id: str, fixed_cost: float, actor: DemoActor) -> dict[str, Any]:
    get_batch(db, batch_id)
    record = db.scalar(
        select(CostRecord).where(CostRecord.batch_id == batch_id, CostRecord.category == "fixed_per_batch")
    )
    require(record is not None, "班次固定成本记录不存在。", 404)
    record.amount = Decimal(str(fixed_cost)).quantize(Decimal("0.01"))
    audit(
        db,
        actor,
        "cost.update_fixed",
        "batch",
        batch_id,
        batch_id=batch_id,
        details={"fixed_cost": float(record.amount)},
    )
    return {"batch_id": batch_id, "fixed_cost": float(record.amount)}


def batch_summary(db: Session, batch_id: str) -> dict[str, Any]:
    batch = get_batch(db, batch_id)
    orders = db.scalars(
        select(Order)
        .where(Order.batch_id == batch_id)
        .options(selectinload(Order.parcels), selectinload(Order.items))
    ).unique().all()
    parcels = [parcel for order in orders for parcel in order.parcels]
    issues = db.scalars(select(Issue).where(Issue.batch_id == batch_id)).all()
    costs = {item.category: item.amount for item in db.scalars(select(CostRecord).where(CostRecord.batch_id == batch_id)).all()}
    food_amount = sum((order.amount for order in orders), Decimal("0"))
    fully_refunded = [order for order in orders if order.parcels and all(p.status == "refunded" for p in order.parcels)]
    refund_amount = sum((order.amount for order in fully_refunded), Decimal("0"))
    paid_orders = len(orders) - len(fully_refunded)
    revenue = (food_amount - refund_amount) * batch.commission_rate + batch.delivery_fee * paid_orders
    variable = costs.get("variable_per_order", Decimal("0")) * len(orders)
    fixed = costs.get("fixed_per_batch", Decimal("0"))
    status_counts = {status: sum(1 for parcel in parcels if parcel.status == status) for status in (
        "pending",
        "ready",
        "picked",
        "campus",
        "out",
        "delivered",
        "missing",
        "pickup_timeout",
        "pickup_abandoned",
        "refunded",
    )}
    return {
        "batch": {
            "id": batch.id,
            "name": batch.name,
            "status": batch.status,
            "capacity": batch.capacity,
            "cutoff_at": batch.cutoff_at.isoformat(),
            "depart_at": batch.depart_at.isoformat(),
            "delivery_window": [batch.delivery_start_at.isoformat(), batch.delivery_end_at.isoformat()],
        },
        "counts": {
            "orders": len(orders),
            "parcels": len(parcels),
            "open_issues": sum(1 for issue in issues if issue.status == "open"),
            **status_counts,
        },
        "economics": {
            "food_amount": float(food_amount),
            "revenue": float(revenue),
            "variable_cost": float(variable),
            "fixed_cost": float(fixed),
            "contribution": float(revenue - variable - fixed),
            "is_demo_estimate": True,
        },
    }


def merchant_dashboard(db: Session, batch_id: str, merchant_id: str) -> dict[str, Any]:
    merchant = db.get(Merchant, merchant_id)
    require(merchant is not None, "商家不存在。", 404)
    orders = list_orders(db, batch_id, merchant_id)
    product_totals: dict[str, dict[str, Any]] = {}
    for order in orders:
        for item in order["items"]:
            entry = product_totals.setdefault(
                item["product_id"], {"product_id": item["product_id"], "name": item["name"], "quantity": 0}
            )
            entry["quantity"] += item["quantity"]
    return {
        "merchant": {"id": merchant.id, "name": merchant.name, "zone": merchant.zone, "status": merchant.status},
        "batch_id": batch_id,
        "orders": orders,
        "production_summary": list(product_totals.values()),
    }
