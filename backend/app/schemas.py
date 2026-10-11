from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(ge=1, le=20)


class OrderCreate(BaseModel):
    batch_id: str = "B001"
    merchant_id: str
    delivery_point_id: str
    student_alias: str = Field(default="演示新用户", min_length=1, max_length=80)
    items: list[OrderItemCreate] = Field(min_length=1)


class HandoffCreate(BaseModel):
    actual_count: int = Field(ge=0)
    picked_parcel_ids: list[str] | None = None
    missing_parcel_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_missing_parcels(self):
        if len(self.missing_parcel_ids) != len(set(self.missing_parcel_ids)):
            raise ValueError("缺袋餐袋编号不能重复。")
        if self.picked_parcel_ids is not None:
            if len(self.picked_parcel_ids) != len(set(self.picked_parcel_ids)):
                raise ValueError("实装餐袋编号不能重复。")
            if set(self.picked_parcel_ids) & set(self.missing_parcel_ids):
                raise ValueError("同一餐袋不能同时标记为实装和缺袋。")
        return self


class EarlyCloseAuthorizationCreate(BaseModel):
    reason: str = Field(min_length=2, max_length=240)


class DemoClockSetRequest(BaseModel):
    current_at: datetime


class ResolveIssueRequest(BaseModel):
    resolution: str = Field(default="模拟退款（无真实资金动作）", min_length=1, max_length=240)


class CostUpdateRequest(BaseModel):
    fixed_cost: float = Field(ge=0, le=2000)


class ApiMessage(BaseModel):
    message: str

    model_config = ConfigDict(from_attributes=True)
