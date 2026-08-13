import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.category import Category
from app.models.product import Product
from app.schemas.product import ProductListResponse, ProductOut

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
async def list_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    search: Optional[str] = None,
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None,
    db: AsyncSession = Depends(get_db),
) -> ProductListResponse:
    filters = [Product.is_active == True]  # noqa: E712

    if category:
        filters.append(Product.category_id == Category.id)
        filters.append(Category.slug == category)

    if search:
        pattern = f"%{search}%"
        filters.append(Product.name.ilike(pattern) | Product.description.ilike(pattern))

    if min_price is not None:
        filters.append(Product.price >= min_price)

    if max_price is not None:
        filters.append(Product.price <= max_price)

    total = await db.scalar(select(func.count(Product.id)).select_from(Product).where(*filters)) or 0

    result = await db.scalars(
        select(Product)
        .where(*filters)
        .order_by(Product.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list(result.all())

    return ProductListResponse(
        items=[ProductOut.model_validate(p) for p in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProductOut:
    product = await db.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return ProductOut.model_validate(product)
