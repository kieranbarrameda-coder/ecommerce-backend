import uuid
from datetime import date, timedelta
from decimal import Decimal

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models.address import Address
from app.models.cart import Cart, CartItem
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product
from app.models.user import User
from app.schemas.order import CreateOrderRequest, OrderListResponse, OrderOut
from app.schemas.payment import PaymentIntentResponse

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(prefix="/orders", tags=["orders"])


async def _order_to_out(db: AsyncSession, order: Order) -> OrderOut:
    items = await db.scalars(
        select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
    )
    return OrderOut(
        id=order.id,
        status=order.status,
        total_amount=order.total_amount,
        shipping_address_id=order.shipping_address_id,
        payment_intent_id=order.payment_intent_id,
        estimated_delivery_date=order.estimated_delivery_date,
        created_at=order.created_at,
        items=list(items.all()),
    )


async def _get_owned_order(db: AsyncSession, user: User, order_id: uuid.UUID) -> Order:
    order = await db.get(Order, order_id)
    if order is None or order.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return order


def _add_business_days(start: date, days: int) -> date:
    result = start
    added = 0
    while added < days:
        result += timedelta(days=1)
        if result.weekday() < 5:
            added += 1
    return result


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    body: CreateOrderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderOut:
    cart = await db.scalar(select(Cart).where(Cart.user_id == user.id))
    rows = []
    if cart is not None:
        result = await db.execute(
            select(CartItem, Product)
            .join(Product, CartItem.product_id == Product.id)
            .where(CartItem.cart_id == cart.id)
            .order_by(CartItem.id)
        )
        rows = result.all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cart is empty",
        )

    address = await db.get(Address, body.shipping_address_id)
    if address is None or address.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipping address not found",
        )

    order = Order(
        user_id=user.id,
        status=OrderStatus.pending,
        total_amount=Decimal("0"),
        shipping_address_id=address.id,
        payment_intent_id=None,
        estimated_delivery_date=_add_business_days(date.today(), 5),
    )
    db.add(order)
    await db.flush()

    total = Decimal("0")
    for item, product in rows:
        failed_product_id = product.id
        failed_product_name = product.name
        stock_stmt = (
            update(Product)
            .where(Product.id == product.id, Product.stock_quantity >= item.quantity)
            .values(stock_quantity=Product.stock_quantity - item.quantity)
            .returning(Product.stock_quantity)
        )
        if await db.scalar(stock_stmt) is None:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Not enough stock for '{failed_product_name}'",
            )
        unit_price = product.price
        total += unit_price * item.quantity
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=unit_price,
            )
        )

    order.total_amount = total

    await db.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
    await db.commit()
    await db.refresh(order)
    return await _order_to_out(db, order)


@router.get("", response_model=OrderListResponse)
async def list_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderListResponse:
    base = select(Order).where(Order.user_id == user.id)

    total = await db.scalar(select(func.count(Order.id)).select_from(Order).where(Order.user_id == user.id)) or 0

    orders = await db.scalars(
        base.order_by(Order.created_at.desc()).offset((page - 1) * limit).limit(limit)
    )

    items = [await _order_to_out(db, order) for order in orders.all()]
    return OrderListResponse(items=items, total=total, page=page, limit=limit)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderOut:
    order = await _get_owned_order(db, user, order_id)
    return await _order_to_out(db, order)


@router.post("/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderOut:
    order = await _get_owned_order(db, user, order_id)
    if order.status != OrderStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending orders can be cancelled",
        )

    items = await db.scalars(select(OrderItem).where(OrderItem.order_id == order.id))
    for item in items.all():
        await db.execute(
            update(Product)
            .where(Product.id == item.product_id)
            .values(stock_quantity=Product.stock_quantity + item.quantity)
        )

    order.status = OrderStatus.cancelled
    await db.commit()
    await db.refresh(order)
    return await _order_to_out(db, order)


@router.post("/{order_id}/pay", response_model=PaymentIntentResponse)
async def pay_order(
    order_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentIntentResponse:
    order = await _get_owned_order(db, user, order_id)
    if order.status != OrderStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending orders can be paid",
        )

    if order.payment_intent_id:
        payment_intent = stripe.PaymentIntent.retrieve(order.payment_intent_id)
    else:
        payment_intent = stripe.PaymentIntent.create(
            amount=int(order.total_amount * 100),
            currency="php",
            metadata={"order_id": str(order.id)},
        )
        order.payment_intent_id = payment_intent.id
        await db.commit()

    return PaymentIntentResponse(
        client_secret=payment_intent.client_secret,
        order_id=order.id,
        amount=order.total_amount,
    )
