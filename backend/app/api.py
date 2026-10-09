from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import services
from .auth import DemoActor, get_demo_actor, require_merchant_scope, require_role
from .database import get_db
from .models import AuditLog, Issue, Merchant, Order, Parcel, PickupHandoff, PickupRoute, PickupStop, Product
from .schemas import CostUpdateRequest, HandoffCreate, OrderCreate, ResolveIssueRequest
from .seed import seed_demo_data


router = APIRouter(prefix="/api")


def mutation(
    db: Session,
    key: str | None,
    action: str,
    operation,
) -> dict:
    return services.execute_idempotent(db, key, action, operation)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ziyang-campus-demo-api", "demo_only": True}


@router.get("/demo/info")
def demo_info() -> dict:
    return {
        "name": "午点通 · 资阳校园集运 Demo v0.1",
        "demo_only": True,
        "authentication": "X-Demo-Role 等请求头仅用于演示流程隔离，不是真实登录或身份认证。",
        "external_integrations": [],
        "notices": [
            "所有商家、订单、菜单、金额和交付点均为虚构演示数据。",
            "没有真实支付、退款、短信、微信或学校系统接口。",
            "学校准入、交付点和实际线路均待线下核实。",
        ],
    }


@router.post("/demo/reset")
def reset_demo(
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
) -> dict:
    require_role(actor, "operations")
    result = seed_demo_data(db, reset=True)
    return {**result, "message": "已恢复固定演示种子。", "demo_only": True}


@router.get("/batches/{batch_id}/summary")
def get_batch_summary(batch_id: str, db: Session = Depends(get_db)) -> dict:
    return services.batch_summary(db, batch_id)


@router.get("/merchants")
def get_merchants(db: Session = Depends(get_db)) -> list[dict]:
    merchants = db.scalars(select(Merchant).order_by(Merchant.id)).all()
    return [
        {
            "id": merchant.id,
            "name": merchant.name,
            "zone": merchant.zone,
            "address": merchant.address,
            "capacity": merchant.capacity,
            "status": merchant.status,
            "products": [
                {"id": product.id, "name": product.name, "price": float(product.price), "active": product.active}
                for product in db.scalars(
                    select(Product).where(Product.merchant_id == merchant.id).order_by(Product.id)
                ).all()
            ],
        }
        for merchant in merchants
    ]


@router.get("/batches/{batch_id}/orders")
def get_orders(
    batch_id: str,
    merchant_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
) -> list[dict]:
    require_role(actor, "merchant", "operations")
    if actor.role == "merchant":
        require_merchant_scope(actor, actor.merchant_id or "")
        if merchant_id and merchant_id != actor.merchant_id:
            require_merchant_scope(actor, merchant_id)
        merchant_id = actor.merchant_id
    return services.list_orders(db, batch_id, merchant_id)


@router.post("/orders", status_code=201)
def post_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    require_role(actor, "student", "operations")
    return mutation(db, idempotency_key, "order.create", lambda: services.create_order(db, payload, actor))


@router.get("/orders/{order_id}")
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
) -> dict:
    require_role(actor, "student", "operations")
    return services.get_order_detail(db, order_id)


@router.post("/orders/{order_id}/accept")
def post_accept_order(
    order_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    order = db.get(Order, order_id)
    services.require(order is not None, "订单不存在。", 404)
    require_merchant_scope(actor, order.merchant_id)
    return mutation(
        db,
        idempotency_key,
        f"merchant.accept_order:{order_id}",
        lambda: services.accept_order(db, order_id, actor),
    )


@router.post("/parcels/{parcel_id}/pack")
def post_pack_parcel(
    parcel_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    parcel = db.get(Parcel, parcel_id)
    services.require(parcel is not None, "餐袋不存在。", 404)
    require_merchant_scope(actor, parcel.merchant_id)
    return mutation(
        db,
        idempotency_key,
        f"merchant.pack_parcel:{parcel_id}",
        lambda: services.pack_parcel(db, parcel_id, actor),
    )


@router.post("/batches/{batch_id}/cutoff")
def post_cutoff(
    batch_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    require_role(actor, "operations")
    return mutation(db, idempotency_key, f"batch.cutoff:{batch_id}", lambda: services.cutoff_batch(db, batch_id, actor))


@router.get("/batches/{batch_id}/merchants/{merchant_id}/dashboard")
def get_merchant_dashboard(
    batch_id: str,
    merchant_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
) -> dict:
    require_merchant_scope(actor, merchant_id)
    return services.merchant_dashboard(db, batch_id, merchant_id)


@router.post("/batches/{batch_id}/merchants/{merchant_id}/accept")
def post_merchant_accept(
    batch_id: str,
    merchant_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    require_merchant_scope(actor, merchant_id)
    return mutation(
        db,
        idempotency_key,
        f"merchant.accept:{batch_id}:{merchant_id}",
        lambda: services.accept_merchant_orders(db, batch_id, merchant_id, actor),
    )


@router.post("/batches/{batch_id}/merchants/{merchant_id}/pack")
def post_merchant_pack(
    batch_id: str,
    merchant_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    require_merchant_scope(actor, merchant_id)
    return mutation(
        db,
        idempotency_key,
        f"merchant.pack:{batch_id}:{merchant_id}",
        lambda: services.pack_merchant(db, batch_id, merchant_id, actor),
    )


@router.get("/batches/{batch_id}/route")
def get_route(
    batch_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
) -> dict:
    require_role(actor, "driver", "operations")
    route = db.scalar(select(PickupRoute).where(PickupRoute.batch_id == batch_id))
    if route is None:
        services.require(False, "班次取货线路不存在。", 404)
    stops = db.scalars(
        select(PickupStop).where(PickupStop.route_id == route.id).order_by(PickupStop.sequence)
    ).all()
    handoffs = {
        item.stop_id: item
        for item in db.scalars(select(PickupHandoff).where(PickupHandoff.stop_id.in_([stop.id for stop in stops]))).all()
    }
    parcel_rows: dict[str, list[Parcel]] = {}
    for stop in stops:
        parcel_rows[stop.id] = db.scalars(
            select(Parcel)
            .join(Order)
            .where(Order.batch_id == batch_id, Parcel.merchant_id == stop.merchant_id)
            .order_by(Parcel.id)
        ).all()
    return {
        "id": route.id,
        "batch_id": batch_id,
        "name": route.name,
        "stops": [
            {
                "id": stop.id,
                "merchant_id": stop.merchant_id,
                "sequence": stop.sequence,
                "planned_pickup_at": stop.planned_pickup_at.isoformat(),
                "planned_count": len(parcel_rows[stop.id]),
                "ready_parcel_ids": [parcel.id for parcel in parcel_rows[stop.id] if parcel.status == "ready"],
                "parcel_status_counts": {
                    status: sum(1 for parcel in parcel_rows[stop.id] if parcel.status == status)
                    for status in ("pending", "ready", "picked", "missing", "refunded", "delivered")
                },
                "parcel_manifest": [
                    {"parcel_id": parcel.id, "order_id": parcel.order_id, "status": parcel.status}
                    for parcel in parcel_rows[stop.id]
                ],
                "handoff": None
                if stop.id not in handoffs
                else {
                    "planned_count": handoffs[stop.id].planned_count,
                    "actual_count": handoffs[stop.id].actual_count,
                    "created_at": handoffs[stop.id].created_at.isoformat(),
                },
            }
            for stop in stops
        ],
    }


@router.post("/pickup-stops/{stop_id}/handoff")
def post_handoff(
    stop_id: str,
    payload: HandoffCreate,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    require_role(actor, "driver", "operations")
    return mutation(
        db,
        idempotency_key,
        f"pickup.handoff:{stop_id}",
        lambda: services.pickup_handoff(db, stop_id, payload, actor),
    )


@router.post("/batches/{batch_id}/depart")
def post_depart(
    batch_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    require_role(actor, "driver", "operations")
    return mutation(db, idempotency_key, f"batch.depart:{batch_id}", lambda: services.depart_batch(db, batch_id, actor))


@router.post("/batches/{batch_id}/campus-receive")
def post_campus_receive(
    batch_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    require_role(actor, "campus", "operations")
    return mutation(db, idempotency_key, f"campus.receive:{batch_id}", lambda: services.campus_receive(db, batch_id, actor))


@router.post("/batches/{batch_id}/delivery/assign")
def post_assign_delivery(
    batch_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    require_role(actor, "campus", "operations")
    return mutation(db, idempotency_key, f"delivery.assign:{batch_id}", lambda: services.assign_delivery(db, batch_id, actor))


@router.post("/batches/{batch_id}/delivery/complete")
def post_complete_delivery(
    batch_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    require_role(actor, "campus", "operations")
    return mutation(db, idempotency_key, f"delivery.complete:{batch_id}", lambda: services.complete_delivery(db, batch_id, actor))


@router.get("/batches/{batch_id}/delivery-tasks")
def get_delivery_tasks(
    batch_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
) -> list[dict]:
    require_role(actor, "campus", "operations")
    return services.list_delivery_tasks(db, batch_id)


@router.post("/delivery-tasks/{task_id}/parcels/{parcel_id}/deliver")
def post_deliver_task_parcel(
    task_id: int,
    parcel_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    require_role(actor, "campus", "operations")
    return mutation(
        db,
        idempotency_key,
        f"delivery.deliver_parcel:{task_id}:{parcel_id}",
        lambda: services.deliver_task_parcel(db, task_id, parcel_id, actor),
    )


@router.get("/batches/{batch_id}/issues")
def get_issues(
    batch_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
) -> list[dict]:
    require_role(actor, "operations")
    issues = db.scalars(select(Issue).where(Issue.batch_id == batch_id).order_by(Issue.created_at.desc())).all()
    return [
        {
            "id": issue.id,
            "merchant_id": issue.merchant_id,
            "order_id": issue.order_id,
            "parcel_id": issue.parcel_id,
            "type": issue.type,
            "status": issue.status,
            "resolution": issue.resolution,
            "created_at": issue.created_at.isoformat(),
            "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
        }
        for issue in issues
    ]


@router.post("/issues/{issue_id}/resolve")
def post_resolve_issue(
    issue_id: str,
    payload: ResolveIssueRequest,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    require_role(actor, "operations")
    return mutation(
        db,
        idempotency_key,
        f"issue.resolve:{issue_id}",
        lambda: services.resolve_issue(db, issue_id, payload.resolution, actor),
    )


@router.put("/batches/{batch_id}/costs/fixed")
def put_fixed_cost(
    batch_id: str,
    payload: CostUpdateRequest,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    require_role(actor, "operations")
    return mutation(
        db,
        idempotency_key,
        f"cost.update_fixed:{batch_id}",
        lambda: services.update_fixed_cost(db, batch_id, payload.fixed_cost, actor),
    )


@router.get("/batches/{batch_id}/audit-logs")
def get_audit_logs(
    batch_id: str,
    db: Session = Depends(get_db),
    actor: DemoActor = Depends(get_demo_actor),
) -> list[dict]:
    require_role(actor, "operations")
    logs = db.scalars(
        select(AuditLog).where(AuditLog.batch_id == batch_id).order_by(AuditLog.id.desc())
    ).all()
    return [
        {
            "id": log.id,
            "actor_role": log.actor_role,
            "actor_id": log.actor_id,
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "details": log.details,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
