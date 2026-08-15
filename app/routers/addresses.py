import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.address import Address
from app.models.user import User
from app.schemas.address import AddressCreate, AddressOut, AddressUpdate

router = APIRouter(prefix="/users/me/addresses", tags=["addresses"])


async def _get_owned_address(db: AsyncSession, user: User, address_id: uuid.UUID) -> Address:
    address = await db.get(Address, address_id)
    if address is None or address.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found",
        )
    return address


async def _clear_other_defaults(db: AsyncSession, user: User, exclude_id: uuid.UUID | None = None) -> None:
    stmt = (
        update(Address)
        .where(Address.user_id == user.id, Address.is_default.is_(True))
        .values(is_default=False)
    )
    if exclude_id is not None:
        stmt = stmt.where(Address.id != exclude_id)
    await db.execute(stmt)


@router.get("", response_model=list[AddressOut])
async def list_addresses(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AddressOut]:
    addresses = await db.scalars(
        select(Address)
        .where(Address.user_id == user.id)
        .order_by(Address.is_default.desc(), Address.id)
    )
    return list(addresses.all())


@router.post("", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
async def create_address(
    body: AddressCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AddressOut:
    count = (
        await db.scalar(
            select(func.count(Address.id)).select_from(Address).where(Address.user_id == user.id)
        )
        or 0
    )

    data = body.model_dump()
    if count == 0:
        data["is_default"] = True
    elif data["is_default"]:
        await _clear_other_defaults(db, user)

    address = Address(user_id=user.id, **data)
    db.add(address)
    await db.commit()
    await db.refresh(address)
    return address


@router.patch("/{address_id}", response_model=AddressOut)
async def update_address(
    address_id: uuid.UUID,
    body: AddressUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AddressOut:
    address = await _get_owned_address(db, user, address_id)

    data = body.model_dump(exclude_unset=True)

    if address.is_default and data.get("is_default") is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot unset the only default address",
        )

    if data.get("is_default") is True:
        await _clear_other_defaults(db, user, exclude_id=address.id)

    for key, value in data.items():
        setattr(address, key, value)

    await db.commit()
    await db.refresh(address)
    return address


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    address = await _get_owned_address(db, user, address_id)

    if address.is_default:
        others = await db.scalars(
            select(Address)
            .where(Address.user_id == user.id, Address.id != address.id)
            .order_by(Address.id)
        )
        other = others.first()
        if other is not None:
            other.is_default = True

    await db.delete(address)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
