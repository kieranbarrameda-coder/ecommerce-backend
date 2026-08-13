import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.order import OrderStatus


class CreateOrderRequest(BaseModel):
    shipping_address_id: uuid.UUID


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    unit_price: Decimal


class OrderOut(BaseModel):
    id: uuid.UUID
    status: OrderStatus
    total_amount: Decimal
    shipping_address_id: uuid.UUID
    payment_intent_id: Optional[str]
    estimated_delivery_date: Optional[date]
    created_at: datetime
    items: list[OrderItemOut]


class OrderListResponse(BaseModel):
    items: list[OrderOut]
    total: int
    page: int
    limit: int
