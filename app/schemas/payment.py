import uuid
from decimal import Decimal

from pydantic import BaseModel


class PaymentIntentResponse(BaseModel):
    client_secret: str
    order_id: uuid.UUID
    amount: Decimal
