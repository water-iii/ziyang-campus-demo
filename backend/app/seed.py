from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .database import Base
from .models import (
    AuditLog,
    Batch,
    CostRecord,
    DeliveryPoint,
    Merchant,
    Order,
    OrderItem,
    Parcel,
    PickupRoute,
    PickupStop,
    Product,
    School,
)


MERCHANTS = [
    ("m1", "梅西·米饭研究所", "梅西商圈", "演示地址 A（待实测）", "11:05"),
    ("m2", "梅西·香酥鸡厨房", "梅西商圈", "演示地址 B（待实测）", "11:15"),
    ("m3", "达高·川味小馆", "达高商圈", "演示地址 C（待实测）", "11:25"),
]

PRODUCTS = [
    ("p11", "m1", "香菇鸡腿饭", "18.00"),
    ("p12", "m1", "红烧牛肉饭", "22.00"),
    ("p13", "m1", "双拼便当", "24.00"),
    ("p21", "m2", "香酥鸡腿套餐", "20.00"),
    ("p22", "m2", "鸡米花盖饭", "17.00"),
    ("p23", "m2", "照烧鸡排饭", "21.00"),
    ("p31", "m3", "宫保鸡丁饭", "19.00"),
    ("p32", "m3", "青椒肉丝盖饭", "18.00"),
    ("p33", "m3", "家常小炒套餐", "23.00"),
]


def seed_demo_data(db: Session, *, reset: bool = False) -> dict[str, int | str]:
    if not reset and db.scalar(select(func.count()).select_from(Batch)):
        return seed_counts(db)

    if reset:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(delete(table))
        db.flush()

    school = School(id="school-zy", name="资阳环境科技职业学院", authorization_status="unverified")
    db.add(school)
    db.flush()
    db.add_all(
        [
            DeliveryPoint(id="point-a", school_id=school.id, name="指定交接点 A（演示）", status="unverified"),
            DeliveryPoint(id="point-b", school_id=school.id, name="指定交接点 B（演示）", status="unverified"),
        ]
    )
    db.add_all(
        [
            Merchant(id=mid, name=name, zone=zone, address=address, capacity=60, status="demo")
            for mid, name, zone, address, _time in MERCHANTS
        ]
    )
    db.flush()
    db.add_all(
        [Product(id=pid, merchant_id=mid, name=name, price=Decimal(price), active=True) for pid, mid, name, price in PRODUCTS]
    )

    demo_day = datetime(2026, 10, 10)
    batch = Batch(
        id="B001",
        school_id=school.id,
        name="午餐第一班 B001",
        cutoff_at=demo_day.replace(hour=10, minute=40),
        depart_at=demo_day.replace(hour=11, minute=30),
        delivery_start_at=demo_day.replace(hour=12, minute=10),
        delivery_end_at=demo_day.replace(hour=12, minute=30),
        capacity=60,
        status="open",
        delivery_fee=Decimal("2.50"),
        commission_rate=Decimal("0.0800"),
    )
    db.add(batch)
    db.flush()
    route = PickupRoute(id="R001", batch_id=batch.id, name="梅西—达高城区取货线")
    db.add(route)
    db.flush()
    for sequence, (mid, _name, _zone, _address, pickup_time) in enumerate(MERCHANTS, start=1):
        hour, minute = (int(part) for part in pickup_time.split(":"))
        db.add(
            PickupStop(
                id=f"S{sequence:03d}",
                route_id=route.id,
                merchant_id=mid,
                sequence=sequence,
                planned_pickup_at=demo_day.replace(hour=hour, minute=minute),
            )
        )
    db.flush()

    products_by_merchant: dict[str, list[tuple[str, str, str, str]]] = {}
    for product in PRODUCTS:
        products_by_merchant.setdefault(product[1], []).append(product)

    two_bag_indices = {4, 11, 18, 25}
    for index in range(30):
        merchant_id = "m1" if index < 12 else ("m2" if index < 22 else "m3")
        product = products_by_merchant[merchant_id][index % 3]
        bag_count = 2 if index in two_bag_indices else 1
        order_id = f"O{260801 + index}"
        amount = Decimal(product[3]) * bag_count
        order = Order(
            id=order_id,
            batch_id=batch.id,
            merchant_id=merchant_id,
            delivery_point_id="point-a" if index % 2 == 0 else "point-b",
            student_alias=f"演示用户{index + 1:02d}",
            amount=amount,
            created_at=demo_day.replace(hour=10, minute=index % 40),
            mock_paid=True,
        )
        order.items.append(
            OrderItem(product_id=product[0], quantity=bag_count, unit_price=Decimal(product[3]))
        )
        for parcel_number in range(1, bag_count + 1):
            order.parcels.append(
                Parcel(
                    id=f"P{260801 + index}-{parcel_number}",
                    merchant_id=merchant_id,
                    status="pending",
                )
            )
        db.add(order)

    # 先固化所有被引用实体，再写不带 ORM relationship 的成本与审计行；
    # 这也让 SQLite 外键开启时的种子顺序保持确定。
    db.flush()
    db.add_all(
        [
            CostRecord(batch_id=batch.id, category="variable_per_order", amount=Decimal("2.05"), note="演示单均变动成本"),
            CostRecord(batch_id=batch.id, category="fixed_per_batch", amount=Decimal("90.00"), note="演示单班固定成本"),
        ]
    )
    db.add(
        AuditLog(
            batch_id=batch.id,
            actor_role="operations",
            actor_id="demo-seed",
            action="demo.reset",
            entity_type="batch",
            entity_id=batch.id,
            details={"orders": 30, "parcels": 34, "notice": "全部为虚构演示数据"},
        )
    )
    db.flush()
    return seed_counts(db)


def seed_counts(db: Session) -> dict[str, int | str]:
    return {
        "batch_id": "B001",
        "orders": int(db.scalar(select(func.count()).select_from(Order)) or 0),
        "parcels": int(db.scalar(select(func.count()).select_from(Parcel)) or 0),
        "merchants": int(db.scalar(select(func.count()).select_from(Merchant)) or 0),
    }
