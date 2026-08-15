import logging
import uuid

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.order import Order, OrderStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _set_order_status_from_event(db: AsyncSession, event: dict, new_status: OrderStatus) -> None:
    order_id = (event["data"]["object"].to_dict().get("metadata") or {}).get("order_id")
    if not order_id:
        logger.warning("Webhook event %s missing order_id in metadata", event["type"])
        return
    try:
        order = await db.get(Order, uuid.UUID(order_id))
    except ValueError:
        logger.warning("Webhook event %s has invalid order_id %s", event["type"], order_id)
        return
    if order is None:
        logger.warning("Webhook event %s references unknown order %s", event["type"], order_id)
        return
    order.status = new_status
    await db.commit()


@router.post("/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    event_type = event["type"]
    if event_type == "payment_intent.succeeded":
        await _set_order_status_from_event(db, event, OrderStatus.paid)
    elif event_type == "payment_intent.payment_failed":
        await _set_order_status_from_event(db, event, OrderStatus.failed)

    return {"status": "ok"}
