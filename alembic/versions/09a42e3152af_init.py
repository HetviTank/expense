"""init

Revision ID: 09a42e3152af
Revises: 
Create Date: 2025-08-20 12:03:28.449142

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09a42e3152af'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create users and expenses tables"""

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("email", sa.String, unique=True, index=True, nullable=False),
        sa.Column("password", sa.String, nullable=False),
        sa.Column("role", sa.String, nullable=False, server_default="employee"),
    )

    # Create expenses table
    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("description", sa.String),
        sa.Column("bill_image", sa.String),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Downgrade schema: drop expenses and users tables"""
    op.drop_table("expenses")
    op.drop_table("users")
