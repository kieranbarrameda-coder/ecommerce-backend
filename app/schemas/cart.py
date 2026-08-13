import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.product import ProductOut


class AddCartItemRequest(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1)


class UpdateCartItemRequest(BaseModel):
    quantity: int = Field(ge=1)


class CartItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    product: ProductOut


class CartOut(BaseModel):
    id: uuid.UUID
    items: list[CartItemOut]
    total_items: int
    subtotal: Decimal
