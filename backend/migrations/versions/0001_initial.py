"""初始表结构。

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-25
"""

from alembic import op

from backend.app.db.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 初版直接由模型元数据建表，保证模型与迁移一致；后续变更使用显式迁移。
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
