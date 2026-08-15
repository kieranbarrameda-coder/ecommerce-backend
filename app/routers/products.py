import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_admin_user
from app.database import get_db
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.schemas.product import ProductCreate, ProductListResponse, ProductOut, ProductUpdate

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


async def _ensure_category_exists(db: AsyncSession, category_id: uuid.UUID) -> None:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> ProductOut:
    if body.category_id is not None:
        await _ensure_category_exists(db, body.category_id)

    product = Product(
        category_id=body.category_id,
        name=body.name,
        description=body.description,
        price=body.price,
        stock_quantity=body.stock_quantity,
        sku=body.sku,
        image_urls=body.image_urls,
        is_active=body.is_active,
    )
    db.add(product)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product with this SKU already exists",
        )
    await db.refresh(product)
    return ProductOut.model_validate(product)


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> ProductOut:
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    if body.category_id is not None:
        await _ensure_category_exists(db, body.category_id)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product with this SKU already exists",
        )
    await db.refresh(product)
    return ProductOut.model_validate(product)
