from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header

from .errors import BusinessError


@dataclass(frozen=True)
class DemoActor:
    role: str
    actor_id: str
    merchant_id: str | None = None


def get_demo_actor(
    x_demo_role: str = Header(default="operations", alias="X-Demo-Role"),
    x_demo_actor: str = Header(default="demo-operator", alias="X-Demo-Actor"),
    x_merchant_id: str | None = Header(default=None, alias="X-Merchant-Id"),
) -> DemoActor:
    allowed = {"student", "merchant", "driver", "campus", "operations"}
    if x_demo_role not in allowed:
        raise BusinessError("未知演示角色。", 403)
    if x_demo_role == "merchant" and not x_merchant_id:
        raise BusinessError("商家演示角色必须提供 X-Merchant-Id。", 403)
    return DemoActor(x_demo_role, x_demo_actor, x_merchant_id)


def require_role(actor: DemoActor, *roles: str) -> None:
    if actor.role not in roles:
        raise BusinessError(f"演示角色 {actor.role} 无权执行此操作。", 403)


def require_merchant_scope(actor: DemoActor, merchant_id: str) -> None:
    require_role(actor, "merchant", "operations")
    if actor.role == "merchant" and actor.merchant_id != merchant_id:
        raise BusinessError("商家只能访问和操作自己的非公开业务数据。", 403)
