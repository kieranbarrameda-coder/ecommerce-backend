"""create users, addresses, refresh_tokens

Revision ID: f181d7a2505c
Revises: 
Create Date: 2026-08-12 23:51:43.183360

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f181d7a2505c'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


userrole = postgresql.ENUM("customer", "admin", name="userrole", create_type=False)


def upgrade() -> None:
    """Upgrade schema."""
    userrole.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("role", userrole, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "addresses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("line1", sa.String(), nullable=False),
        sa.Column("line2", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=False),
        sa.Column("province", sa.String(), nullable=False),
        sa.Column("postal_code", sa.String(), nullable=False),
        sa.Column("country", sa.String(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("refresh_tokens")
    op.drop_table("addresses")
    op.drop_table("users")
    userrole.drop(op.get_bind(), checkfirst=True)
