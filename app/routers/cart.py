import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.models.user import User
from app.schemas.cart import AddCartItemRequest, CartOut, CartItemOut, UpdateCartItemRequest
from app.schemas.product import ProductOut

router = APIRouter(prefix="/cart", tags=["cart"])


async def _get_or_create_cart(db: AsyncSession, user: User) -> Cart:
    cart = await db.scalar(select(Cart).where(Cart.user_id == user.id))
    if cart is None:
        cart = Cart(user_id=user.id)
        db.add(cart)
        await db.flush()
    return cart


async def _cart_to_out(db: AsyncSession, cart: Cart) -> CartOut:
    result = await db.execute(
        select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(CartItem.cart_id == cart.id)
        .order_by(CartItem.id)
    )
    rows = result.all()

    items = [
        CartItemOut(
            id=item.id,
            product_id=item.product_id,
            quantity=item.quantity,
            product=ProductOut.model_validate(product),
        )
        for item, product in rows
    ]
    subtotal = sum((product.price * item.quantity for item, product in rows), Decimal("0"))
    total_items = sum(item.quantity for item, _ in rows)

    return CartOut(
        id=cart.id,
        items=items,
        total_items=total_items,
        subtotal=subtotal,
    )


async def _load_user_cart(db: AsyncSession, user: User) -> Optional[Cart]:
    return await db.scalar(select(Cart).where(Cart.user_id == user.id))


async def _get_owned_item(db: AsyncSession, cart: Cart, item_id: uuid.UUID) -> CartItem:
    item = await db.get(CartItem, item_id)
    if item is None or item.cart_id != cart.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found",
        )
    return item


@router.get("", response_model=CartOut)
async def get_cart(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CartOut:
    cart = await _load_user_cart(db, user)
    if cart is None:
        cart = Cart(user_id=user.id)
        db.add(cart)
        await db.commit()
        await db.refresh(cart)
    return await _cart_to_out(db, cart)


@router.post("/items", response_model=CartOut)
async def add_cart_item(
    body: AddCartItemRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CartOut:
    product = await db.get(Product, body.product_id)
    if product is None or not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    cart = await _get_or_create_cart(db, user)

    existing = await db.scalar(
        select(CartItem).where(
            CartItem.cart_id == cart.id,
            CartItem.product_id == body.product_id,
        )
    )
    if existing is not None:
        existing.quantity += body.quantity
        await db.commit()
        return await _cart_to_out(db, cart)

    db.add(CartItem(cart_id=cart.id, product_id=body.product_id, quantity=body.quantity))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(CartItem).where(
                CartItem.cart_id == cart.id,
                CartItem.product_id == body.product_id,
            )
        )
        existing.quantity += body.quantity
        await db.commit()
    return await _cart_to_out(db, cart)


@router.patch("/items/{item_id}", response_model=CartOut)
async def update_cart_item(
    item_id: uuid.UUID,
    body: UpdateCartItemRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CartOut:
    cart = await _load_user_cart(db, user)
    if cart is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found",
        )
    item = await _get_owned_item(db, cart, item_id)
    item.quantity = body.quantity
    await db.commit()
    return await _cart_to_out(db, cart)


@router.delete("/items/{item_id}", response_model=CartOut)
async def remove_cart_item(
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CartOut:
    cart = await _load_user_cart(db, user)
    if cart is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found",
        )
    item = await _get_owned_item(db, cart, item_id)
    await db.delete(item)
    await db.commit()
    return await _cart_to_out(db, cart)
