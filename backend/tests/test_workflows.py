from __future__ import annotations


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
    assert created["order"]["id"] == "O260831"
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
