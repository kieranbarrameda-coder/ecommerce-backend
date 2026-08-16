import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: Optional[uuid.UUID]
    name: str
    description: Optional[str]
    price: Decimal
    stock_quantity: int
    sku: Optional[str]
    image_urls: list[str]
    is_active: bool
    created_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    limit: int


class ProductCreate(BaseModel):
    category_id: Optional[uuid.UUID] = None
    name: str
    description: Optional[str] = None
    price: Decimal
    stock_quantity: int = 0
    sku: Optional[str] = None
    image_urls: list[str] = []
    is_active: bool = True


class ProductUpdate(BaseModel):
    category_id: Optional[uuid.UUID] = None
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    stock_quantity: Optional[int] = None
    sku: Optional[str] = None
    image_urls: Optional[list[str]] = None
    is_active: Optional[bool] = None


class ImageUploadResponse(BaseModel):
    image_urls: list[str]
