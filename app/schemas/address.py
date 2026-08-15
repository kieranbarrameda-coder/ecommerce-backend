import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AddressCreate(BaseModel):
    label: Optional[str] = None
    line1: str
    line2: Optional[str] = None
    city: str
    province: str
    postal_code: str
    country: str
    is_default: bool = False


class AddressUpdate(BaseModel):
    label: Optional[str] = None
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    is_default: Optional[bool] = None


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: Optional[str]
    line1: str
    line2: Optional[str]
    city: str
    province: str
    postal_code: str
    country: str
    is_default: bool
