from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.models import Product


def assert_ok(response, expected: int = 200):
    assert response.status_code == expected, response.text
    return response.json()


def cutoff_accept_pack_all(client, headers):
    assert_ok(client.post("/api/batches/B001/cutoff", headers=headers("operations")))
    for merchant_id in ("m1", "m2", "m3"):
        merchant_headers = headers("merchant", merchant_id=merchant_id)
        assert_ok(client.post(f"/api/batches/B001/merchants/{merchant_id}/accept", headers=merchant_headers))
        assert_ok(client.post(f"/api/batches/B001/merchants/{merchant_id}/pack", headers=merchant_headers))


def handoff(client, headers, stop_id: str, actual_count: int, missing=None, key=None):
    request_headers = headers("driver")
    if key:
        request_headers["Idempotency-Key"] = key
    return client.post(
        f"/api/pickup-stops/{stop_id}/handoff",
        headers=request_headers,
        json={"actual_count": actual_count, "missing_parcel_ids": missing or []},
    )


def test_seed_student_order_cutoff_and_normal_fulfillment(client, headers):
    assert client.get("/", follow_redirects=False).status_code == 307
    initial = assert_ok(client.get("/api/batches/B001/summary"))
    assert initial["counts"]["orders"] == 30
    assert initial["counts"]["parcels"] == 34
    assert initial["batch"]["status"] == "open"

    order_headers = headers("student") | {"Idempotency-Key": "student-order-001"}
    payload = {
        "batch_id": "B001",
        "merchant_id": "m1",
        "delivery_point_id": "point-a",
        "student_alias": "自动化演示用户",
        "items": [{"product_id": "p11", "quantity": 1}],
    }
    created = assert_ok(client.post("/api/orders", headers=order_headers, json=payload), 201)
    assert created["order"]["id"].startswith("O")
    assert len(created["order"]["id"]) == 25
    assert created["order"]["status"] == "awaiting_merchant_acceptance"
    student_lookup = assert_ok(
        client.get(f"/api/orders/{created['order']['id']}", headers=headers("student"))
    )
    assert student_lookup["id"] == created["order"]["id"]
    replayed = assert_ok(client.post("/api/orders", headers=order_headers, json=payload), 201)
    assert replayed["order"]["id"] == created["order"]["id"]
    assert replayed["idempotent_replay"] is True
    assert assert_ok(client.get("/api/batches/B001/summary"))["counts"]["orders"] == 31
    merchant_view = assert_ok(
        client.get(
            "/api/batches/B001/merchants/m1/dashboard",
            headers=headers("merchant", merchant_id="m1"),
        )
    )
    assert created["order"]["id"] in {order["id"] for order in merchant_view["orders"]}

    cutoff_headers = headers("operations") | {"Idempotency-Key": "cutoff-001"}
    cutoff = assert_ok(client.post("/api/batches/B001/cutoff", headers=cutoff_headers))
    assert cutoff["status"] == "cutoff"
    assert assert_ok(client.post("/api/batches/B001/cutoff", headers=cutoff_headers))["idempotent_replay"] is True
    rejected = client.post("/api/orders", headers=headers("student"), json=payload)
    assert rejected.status_code == 409
    assert "已截单" in rejected.json()["detail"]

    for merchant_id in ("m1", "m2", "m3"):
        merchant_headers = headers("merchant", merchant_id=merchant_id)
        assert_ok(client.post(f"/api/batches/B001/merchants/{merchant_id}/accept", headers=merchant_headers))
        assert_ok(client.post(f"/api/batches/B001/merchants/{merchant_id}/pack", headers=merchant_headers))

    route = assert_ok(client.get("/api/batches/B001/route", headers=headers("driver")))
    assert [stop["planned_count"] for stop in route["stops"]] == [15, 11, 9]
    assert len(route["stops"][0]["ready_parcel_ids"]) == 15
    last_stop = route["stops"][-1]
    assert len(last_stop["ready_parcel_ids"]) == 9
    assert datetime.fromisoformat(last_stop["planned_pickup_at"]) <= datetime.fromisoformat(
        last_stop["latest_handoff_at"]
    )
    assert datetime.fromisoformat(last_stop["latest_handoff_at"]) <= datetime.fromisoformat(
        initial["batch"]["depart_at"]
    ) - timedelta(minutes=5)

    assert_ok(handoff(client, headers, "S001", 15))
    assert_ok(handoff(client, headers, "S002", 11))
    assert_ok(handoff(client, headers, "S003", 9))
    assert assert_ok(client.post("/api/batches/B001/depart", headers=headers("driver")))["loaded_parcels"] == 35
    assert assert_ok(client.post("/api/batches/B001/campus-receive", headers=headers("campus")))["received_parcels"] == 35
    assert assert_ok(client.post("/api/batches/B001/delivery/assign", headers=headers("campus")))["tasks"] == 2
    completed = assert_ok(client.post("/api/batches/B001/delivery/complete", headers=headers("campus")))
    assert completed["status"] == "finished"
    final = assert_ok(client.get("/api/batches/B001/summary"))
    assert final["counts"]["delivered"] == 35
    assert final["counts"]["open_issues"] == 0


def test_shortage_keeps_unloaded_order_exception_until_resolution(client, headers):
    cutoff_accept_pack_all(client, headers)

    out_of_order = handoff(client, headers, "S002", 11)
    assert out_of_order.status_code == 409
    assert "上一站" in out_of_order.json()["detail"]

    first_headers_key = "handoff-s001"
    first = assert_ok(handoff(client, headers, "S001", 14, key=first_headers_key))
    assert first["actual_count"] == 14
    replay = assert_ok(handoff(client, headers, "S001", 14, key=first_headers_key))
    assert replay["idempotent_replay"] is True
    duplicate = handoff(client, headers, "S001", 14)
    assert duplicate.status_code == 409
    assert "重复交接" in duplicate.json()["detail"]

    assert_ok(handoff(client, headers, "S002", 11))
    merchant_orders = assert_ok(
        client.get(
            "/api/batches/B001/orders?merchant_id=m3",
            headers=headers("merchant", merchant_id="m3"),
        )
    )
    missing_parcel_id = next(order["parcels"][0]["id"] for order in merchant_orders if len(order["parcels"]) == 1)
    assert_ok(handoff(client, headers, "S003", 8, [missing_parcel_id]))

    assert_ok(client.post("/api/batches/B001/depart", headers=headers("driver")))
    assert_ok(client.post("/api/batches/B001/campus-receive", headers=headers("campus")))
    assert_ok(client.post("/api/batches/B001/delivery/assign", headers=headers("campus")))
    delivery = assert_ok(client.post("/api/batches/B001/delivery/complete", headers=headers("campus")))
    assert delivery["status"] == "delivering"
    summary = assert_ok(client.get("/api/batches/B001/summary"))
    assert summary["counts"]["missing"] == 1
    assert summary["counts"]["delivered"] == 33
    assert summary["counts"]["open_issues"] == 1

    orders_after_depart = assert_ok(
        client.get(
            "/api/batches/B001/orders?merchant_id=m3",
            headers=headers("merchant", merchant_id="m3"),
        )
    )
    missing_order = next(order for order in orders_after_depart if any(p["id"] == missing_parcel_id for p in order["parcels"]))
    assert missing_order["status"] == "pickup_exception"
    assert next(p for p in missing_order["parcels"] if p["id"] == missing_parcel_id)["status"] == "missing"

    issues = assert_ok(client.get("/api/batches/B001/issues", headers=headers("operations")))
    assert len(issues) == 1
    assert issues[0]["type"] == "merchant_handoff_shortage"
    resolution_headers = headers("operations") | {"Idempotency-Key": "refund-ex001"}
    resolved = assert_ok(
        client.post(
            f"/api/issues/{issues[0]['id']}/resolve",
            headers=resolution_headers,
            json={"resolution": "自动化测试模拟退款（无真实资金动作）"},
        )
    )
    assert resolved["real_payment_action"] is False
    assert resolved["parcel_status"] == "refunded"
    assert resolved["batch_status"] == "finished"
    assert assert_ok(
        client.post(
            f"/api/issues/{issues[0]['id']}/resolve",
            headers=resolution_headers,
            json={"resolution": "自动化测试模拟退款（无真实资金动作）"},
        )
    )["idempotent_replay"] is True
    repeated_without_key = client.post(
        f"/api/issues/{issues[0]['id']}/resolve",
        headers=headers("operations"),
        json={"resolution": "再次退款"},
    )
    assert repeated_without_key.status_code == 409


def test_demo_reset_permissions_and_audit(client, headers):
    denied = client.get(
        "/api/batches/B001/merchants/m2/dashboard",
        headers=headers("merchant", merchant_id="m1"),
    )
    assert denied.status_code == 403
    own = assert_ok(
        client.get(
            "/api/batches/B001/merchants/m1/dashboard",
            headers=headers("merchant", merchant_id="m1"),
        )
    )
    assert own["merchant"]["id"] == "m1"
    assert all(order["merchant_id"] == "m1" for order in own["orders"])

    cutoff_accept_pack_all(client, headers)
    logs = assert_ok(client.get("/api/batches/B001/audit-logs", headers=headers("operations")))
    actions = {log["action"] for log in logs}
    assert {"batch.cutoff", "merchant.accept_orders", "merchant.pack"}.issubset(actions)

    reset = assert_ok(client.post("/api/demo/reset", headers=headers("operations")))
    assert reset["orders"] == 30
    assert reset["parcels"] == 34
    summary = assert_ok(client.get("/api/batches/B001/summary"))
    assert summary["batch"]["status"] == "open"
    assert summary["counts"]["orders"] == 30
    assert summary["counts"]["parcels"] == 34


def test_stage3_individual_order_parcel_handoff_and_delivery_trace(client, headers):
    assert_ok(client.post("/api/batches/B001/cutoff", headers=headers("operations")))
    m1_headers = headers("merchant", merchant_id="m1")
    m1_dashboard = assert_ok(client.get("/api/batches/B001/merchants/m1/dashboard", headers=m1_headers))
    first_order = m1_dashboard["orders"][0]
    first_parcel_id = first_order["parcels"][0]["id"]

    cross_store = client.post(
        f"/api/orders/{first_order['id']}/accept",
        headers=headers("merchant", merchant_id="m2"),
    )
    assert cross_store.status_code == 403

    accepted = assert_ok(client.post(f"/api/orders/{first_order['id']}/accept", headers=m1_headers))
    assert accepted["order_id"] == first_order["id"]
    packed = assert_ok(client.post(f"/api/parcels/{first_parcel_id}/pack", headers=m1_headers))
    assert packed["parcel_status"] == "ready"

    remaining_accept = assert_ok(client.post("/api/batches/B001/merchants/m1/accept", headers=m1_headers))
    assert remaining_accept["accepted_orders"] == 11
    remaining_pack = assert_ok(client.post("/api/batches/B001/merchants/m1/pack", headers=m1_headers))
    assert remaining_pack["packed_parcels"] == 13
    for merchant_id in ("m2", "m3"):
        merchant_headers = headers("merchant", merchant_id=merchant_id)
        assert_ok(client.post(f"/api/batches/B001/merchants/{merchant_id}/accept", headers=merchant_headers))
        assert_ok(client.post(f"/api/batches/B001/merchants/{merchant_id}/pack", headers=merchant_headers))

    route = assert_ok(client.get("/api/batches/B001/route", headers=headers("driver")))
    for stop in route["stops"][:2]:
        picked_ids = [parcel["parcel_id"] for parcel in stop["parcel_manifest"]]
        assert_ok(
            client.post(
                f"/api/pickup-stops/{stop['id']}/handoff",
                headers=headers("driver"),
                json={
                    "actual_count": len(picked_ids),
                    "picked_parcel_ids": picked_ids,
                    "missing_parcel_ids": [],
                },
            )
        )
    last_stop = route["stops"][2]
    last_ids = [parcel["parcel_id"] for parcel in last_stop["parcel_manifest"]]
    missing_id = last_ids[-1]
    explicit_handoff = assert_ok(
        client.post(
            f"/api/pickup-stops/{last_stop['id']}/handoff",
            headers=headers("driver"),
            json={
                "actual_count": len(last_ids) - 1,
                "picked_parcel_ids": last_ids[:-1],
                "missing_parcel_ids": [missing_id],
            },
        )
    )
    assert explicit_handoff["picked_parcel_ids"] == last_ids[:-1]
    assert explicit_handoff["missing_parcel_ids"] == [missing_id]

    assert_ok(client.post("/api/batches/B001/depart", headers=headers("driver")))
    assert_ok(client.post("/api/batches/B001/campus-receive", headers=headers("campus")))
    assert_ok(client.post("/api/batches/B001/delivery/assign", headers=headers("campus")))
    tasks = assert_ok(client.get("/api/batches/B001/delivery-tasks", headers=headers("campus")))
    assert len(tasks) == 2
    assert sum(len(task["parcels"]) for task in tasks) == 33
    first_task = tasks[0]
    delivery_parcel = first_task["parcels"][0]["parcel_id"]
    delivered = assert_ok(
        client.post(
            f"/api/delivery-tasks/{first_task['id']}/parcels/{delivery_parcel}/deliver",
            headers=headers("campus"),
        )
    )
    assert delivered["parcel_status"] == "delivered"
    duplicate_delivery = client.post(
        f"/api/delivery-tasks/{first_task['id']}/parcels/{delivery_parcel}/deliver",
        headers=headers("campus"),
    )
    assert duplicate_delivery.status_code == 409

    bulk_complete = assert_ok(client.post("/api/batches/B001/delivery/complete", headers=headers("campus")))
    assert bulk_complete["status"] == "delivering"
    issue = assert_ok(client.get("/api/batches/B001/issues", headers=headers("operations")))[0]
    resolved = assert_ok(
        client.post(
            f"/api/issues/{issue['id']}/resolve",
            headers=headers("operations"),
            json={"resolution": "逐袋追踪测试：模拟退款（无真实资金动作）"},
        )
    )
    assert resolved["batch_status"] == "finished"
    cost_denied = client.put(
        "/api/batches/B001/costs/fixed",
        headers=m1_headers,
        json={"fixed_cost": 125},
    )
    assert cost_denied.status_code == 403
    cost = assert_ok(
        client.put(
            "/api/batches/B001/costs/fixed",
            headers=headers("operations"),
            json={"fixed_cost": 125},
        )
    )
    assert cost["fixed_cost"] == 125
    assert assert_ok(client.get("/api/batches/B001/summary"))["economics"]["fixed_cost"] == 125
    logs = assert_ok(client.get("/api/batches/B001/audit-logs", headers=headers("operations")))
    actions = {log["action"] for log in logs}
    assert {"merchant.accept_order", "merchant.pack_parcel", "delivery.deliver_parcel", "cost.update_fixed"}.issubset(actions)


def test_concurrent_order_creation_uses_unique_ids(client, headers):
    def create(index: int):
        return client.post(
            "/api/orders",
            headers=headers("student", actor=f"concurrent-{index}"),
            json={
                "batch_id": "B001",
                "merchant_id": "m1",
                "delivery_point_id": "point-a",
                "student_alias": f"并发用户{index}",
                "items": [{"product_id": "p11", "quantity": 1}],
            },
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(create, range(8)))

    created = [assert_ok(response, 201)["order"] for response in responses]
    order_ids = {order["id"] for order in created}
    parcel_ids = {order["parcels"][0]["id"] for order in created}
    assert len(order_ids) == 8
    assert len(parcel_ids) == 8
    assert all(order_id.startswith("O") and len(order_id) == 25 for order_id in order_ids)
    assert assert_ok(client.get("/api/batches/B001/summary"))["counts"]["orders"] == 38


def test_order_item_name_price_and_amount_are_historical_snapshots(client, headers):
    payload = {
        "batch_id": "B001",
        "merchant_id": "m1",
        "delivery_point_id": "point-a",
        "student_alias": "快照测试用户",
        "items": [{"product_id": "p11", "quantity": 2}],
    }
    created = assert_ok(client.post("/api/orders", headers=headers("student"), json=payload), 201)["order"]
    assert created["items"] == [
        {"product_id": "p11", "name": "香菇鸡腿饭", "quantity": 2, "unit_price": 18.0}
    ]
    assert created["amount"] == 36.0

    with client.app.state.session_factory.begin() as db:
        product = db.get(Product, "p11")
        product.name = "后续改名商品"
        product.price = 999
        product.active = False

    historical = assert_ok(client.get(f"/api/orders/{created['id']}", headers=headers("student")))
    assert historical["items"] == created["items"]
    assert historical["amount"] == 36.0


def test_seven_of_nine_parcels_timeout_at_stop_deadline_and_require_operations_resolution(client, headers):
    assert_ok(client.post("/api/batches/B001/cutoff", headers=headers("operations")))

    for merchant_id in ("m1", "m2"):
        merchant_headers = headers("merchant", merchant_id=merchant_id)
        assert_ok(client.post(f"/api/batches/B001/merchants/{merchant_id}/accept", headers=merchant_headers))
        assert_ok(client.post(f"/api/batches/B001/merchants/{merchant_id}/pack", headers=merchant_headers))

    route = assert_ok(client.get("/api/batches/B001/route", headers=headers("driver")))
    for stop in route["stops"][:2]:
        assert_ok(handoff(client, headers, stop["id"], stop["planned_count"]))

    m3_headers = headers("merchant", merchant_id="m3")
    assert_ok(client.post("/api/batches/B001/merchants/m3/accept", headers=m3_headers))
    m3_orders = assert_ok(client.get("/api/batches/B001/orders?merchant_id=m3", headers=m3_headers))
    m3_parcel_ids = [parcel["id"] for order in m3_orders for parcel in order["parcels"]]
    assert len(m3_parcel_ids) == 9
    for parcel_id in m3_parcel_ids[:7]:
        assert_ok(client.post(f"/api/parcels/{parcel_id}/pack", headers=m3_headers))

    route = assert_ok(client.get("/api/batches/B001/route", headers=headers("driver")))
    last_stop = route["stops"][2]
    deadline = datetime.fromisoformat(last_stop["latest_handoff_at"])
    before_deadline = (deadline - timedelta(minutes=1)).isoformat()
    clock = assert_ok(
        client.put(
            "/api/demo/clock",
            headers=headers("operations", actor="demo-clock-operator"),
            json={"current_at": before_deadline},
        )
    )
    assert clock["simulated"] is True
    assert clock["current_at"] == before_deadline

    route = assert_ok(client.get("/api/batches/B001/route", headers=headers("driver")))
    last_stop = route["stops"][2]
    assert last_stop["planned_count"] == 9
    assert len(last_stop["ready_parcel_ids"]) == 7
    assert len(last_stop["unready_parcel_ids"]) == 2
    assert last_stop["deadline_reached"] is False
    assert last_stop["partial_handoff_allowed"] is False

    handoff_payload = {
        "actual_count": 7,
        "picked_parcel_ids": last_stop["ready_parcel_ids"],
        "missing_parcel_ids": last_stop["unready_parcel_ids"],
    }
    too_early = client.post(
        "/api/pickup-stops/S003/handoff",
        headers=headers("driver"),
        json=handoff_payload,
    )
    assert too_early.status_code == 409
    assert "最晚交接时间" in too_early.json()["detail"]
    assert "运营提前关闭授权" in too_early.json()["detail"]
    before_deadline_summary = assert_ok(client.get("/api/batches/B001/summary"))
    assert before_deadline_summary["counts"]["pending"] == 2
    assert before_deadline_summary["counts"]["pickup_timeout"] == 0
    assert before_deadline_summary["counts"]["missing"] == 0
    assert assert_ok(client.get("/api/batches/B001/issues", headers=headers("operations"))) == []

    assert_ok(
        client.put(
            "/api/demo/clock",
            headers=headers("operations", actor="demo-clock-operator"),
            json={"current_at": last_stop["latest_handoff_at"]},
        )
    )

    route = assert_ok(client.get("/api/batches/B001/route", headers=headers("driver")))
    last_stop = route["stops"][2]
    assert last_stop["deadline_reached"] is True
    assert last_stop["partial_handoff_allowed"] is True
    invalid_pick = client.post(
        "/api/pickup-stops/S003/handoff",
        headers=headers("driver"),
        json={
            "actual_count": 8,
            "picked_parcel_ids": last_stop["ready_parcel_ids"] + [last_stop["unready_parcel_ids"][0]],
            "missing_parcel_ids": [last_stop["unready_parcel_ids"][1]],
        },
    )
    assert invalid_pick.status_code == 409
    assert "已打包" in invalid_pick.json()["detail"]

    result = assert_ok(
        client.post(
            "/api/pickup-stops/S003/handoff",
            headers=headers("driver"),
            json=handoff_payload,
        )
    )
    assert result["actual_count"] == 7
    assert set(result["timeout_parcel_ids"]) == set(last_stop["unready_parcel_ids"])
    assert result["shortage_parcel_ids"] == []
    assert result["abandoned_parcel_ids"] == []
    assert result["deadline_reached"] is True

    route_after_handoff = assert_ok(client.get("/api/batches/B001/route", headers=headers("driver")))
    last_after_handoff = route_after_handoff["stops"][2]
    assert last_after_handoff["handoff"]["planned_count"] == 9
    assert last_after_handoff["handoff"]["actual_count"] == 7
    assert last_after_handoff["parcel_status_counts"]["picked"] == 7
    assert last_after_handoff["parcel_status_counts"]["pickup_timeout"] == 2
    assert last_after_handoff["parcel_status_counts"]["pending"] == 0
    assert last_after_handoff["parcel_status_counts"]["ready"] == 0

    before_depart = assert_ok(client.get("/api/batches/B001/summary"))
    assert before_depart["counts"]["pickup_timeout"] == 2
    assert before_depart["counts"]["refunded"] == 0
    issues = assert_ok(client.get("/api/batches/B001/issues", headers=headers("operations")))
    assert len(issues) == 2
    assert {issue["type"] for issue in issues} == {"merchant_preparation_timeout"}

    assert assert_ok(client.post("/api/batches/B001/depart", headers=headers("driver")))["loaded_parcels"] == 32
    assert_ok(client.post("/api/batches/B001/campus-receive", headers=headers("campus")))
    assert_ok(client.post("/api/batches/B001/delivery/assign", headers=headers("campus")))
    delivered = assert_ok(client.post("/api/batches/B001/delivery/complete", headers=headers("campus")))
    assert delivered["status"] == "delivering"

    after_delivery = assert_ok(client.get("/api/batches/B001/summary"))
    assert after_delivery["counts"]["delivered"] == 32
    assert after_delivery["counts"]["pickup_timeout"] == 2
    assert after_delivery["counts"]["refunded"] == 0
    m3_after = assert_ok(client.get("/api/batches/B001/orders?merchant_id=m3", headers=m3_headers))
    timeout_parcels = {
        parcel["id"]: (order["status"], parcel["status"])
        for order in m3_after
        for parcel in order["parcels"]
        if parcel["id"] in result["timeout_parcel_ids"]
    }
    assert len(timeout_parcels) == 2
    assert set(timeout_parcels.values()) == {("pickup_exception", "pickup_timeout")}

    for issue in issues:
        resolved = assert_ok(
            client.post(
                f"/api/issues/{issue['id']}/resolve",
                headers=headers("operations", actor="timeout-operator"),
                json={"resolution": "延迟出餐未装车，运营模拟退款（无真实资金动作）"},
            )
        )
        assert resolved["real_payment_action"] is False
    assert resolved["batch_status"] == "finished"

    logs = assert_ok(client.get("/api/batches/B001/audit-logs", headers=headers("operations")))
    assert sum(log["action"] == "issue.open" for log in logs) == 2
    resolution_logs = [log for log in logs if log["action"] == "issue.resolve"]
    assert len(resolution_logs) == 2
    assert {log["actor_id"] for log in resolution_logs} == {"timeout-operator"}


def test_early_close_requires_operations_authorization_and_audit(client, headers):
    assert_ok(client.post("/api/batches/B001/cutoff", headers=headers("operations")))
    merchant_headers = headers("merchant", merchant_id="m1")
    assert_ok(client.post("/api/batches/B001/merchants/m1/accept", headers=merchant_headers))
    orders = assert_ok(client.get("/api/batches/B001/orders?merchant_id=m1", headers=merchant_headers))
    parcel_ids = [parcel["id"] for order in orders for parcel in order["parcels"]]
    assert len(parcel_ids) == 14
    for parcel_id in parcel_ids[:12]:
        assert_ok(client.post(f"/api/parcels/{parcel_id}/pack", headers=merchant_headers))

    route = assert_ok(client.get("/api/batches/B001/route", headers=headers("driver")))
    first_stop = route["stops"][0]
    before_deadline = (
        datetime.fromisoformat(first_stop["latest_handoff_at"]) - timedelta(minutes=1)
    ).isoformat()
    assert_ok(
        client.put(
            "/api/demo/clock",
            headers=headers("operations"),
            json={"current_at": before_deadline},
        )
    )
    route = assert_ok(client.get("/api/batches/B001/route", headers=headers("driver")))
    first_stop = route["stops"][0]
    payload = {
        "actual_count": 12,
        "picked_parcel_ids": first_stop["ready_parcel_ids"],
        "missing_parcel_ids": first_stop["unready_parcel_ids"],
    }
    assert client.post("/api/pickup-stops/S001/handoff", headers=headers("driver"), json=payload).status_code == 409

    driver_denied = client.post(
        "/api/pickup-stops/S001/early-close-authorization",
        headers=headers("driver"),
        json={"reason": "司机自行决定"},
    )
    assert driver_denied.status_code == 403

    authorization = assert_ok(
        client.post(
            "/api/pickup-stops/S001/early-close-authorization",
            headers=headers("operations", actor="ops-supervisor"),
            json={"reason": "为保障固定发车，运营确认提前关闭本站"},
        )
    )
    assert authorization["authorization_id"].startswith("EA")
    route = assert_ok(client.get("/api/batches/B001/route", headers=headers("driver")))
    first_stop = route["stops"][0]
    assert first_stop["early_close_authorized"] is True
    assert first_stop["partial_handoff_allowed"] is True
    result = assert_ok(
        client.post("/api/pickup-stops/S001/handoff", headers=headers("driver"), json=payload)
    )
    assert len(result["abandoned_parcel_ids"]) == 2
    assert result["timeout_parcel_ids"] == []
    assert result["early_close_authorization_id"] == authorization["authorization_id"]
    summary = assert_ok(client.get("/api/batches/B001/summary"))
    assert summary["counts"]["pickup_abandoned"] == 2

    logs = assert_ok(client.get("/api/batches/B001/audit-logs", headers=headers("operations")))
    authorization_logs = [log for log in logs if log["action"] == "pickup.early_close_authorize"]
    assert len(authorization_logs) == 1
    assert authorization_logs[0]["actor_id"] == "ops-supervisor"
    assert authorization_logs[0]["details"]["reason"] == "为保障固定发车，运营确认提前关闭本站"


def test_demo_clock_is_disabled_in_production(workspace_test_dir, headers):
    database_path = (workspace_test_dir / "production.db").as_posix()
    app = create_app(f"sqlite:///{database_path}", app_env="production")
    try:
        with TestClient(app) as production_client:
            assert production_client.get("/api/demo/clock", headers=headers("operations")).status_code == 404
            assert production_client.put(
                "/api/demo/clock",
                headers=headers("operations"),
                json={"current_at": "2026-10-10T11:25:00"},
            ).status_code == 404
            assert production_client.delete("/api/demo/clock", headers=headers("operations")).status_code == 404
    finally:
        app.state.engine.dispose()
