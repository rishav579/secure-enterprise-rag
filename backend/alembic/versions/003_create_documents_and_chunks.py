"""create documents, document_chunks, and document_permissions tables

Revision ID: 003_create_documents_and_chunks
Revises: 002_create_users_table
Create Date: 2026-08-31 11:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

# revision identifiers, used by Alembic.
revision: str = "003_create_documents_and_chunks"
down_revision: Union[str, None] = "002_create_users_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create documents table
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False, server_default="application/pdf"),
        sa.Column(
            "min_role",
            sa.Enum("admin", "employee", name="user_role", native_enum=False, length=32),
            nullable=False,
            server_default="employee",
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("doc_metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_id"), "documents", ["id"], unique=False)
    op.create_index(op.f("ix_documents_tenant_id"), "documents", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_documents_owner_id"), "documents", ["owner_id"], unique=False)
    op.create_index("ix_documents_tenant_file_hash", "documents", ["tenant_id", "file_hash"], unique=False)

    # 2. Create document_permissions table
    op.create_table(
        "document_permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("permission", sa.String(length=32), nullable=False, server_default="read"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "user_id", name="uq_document_permissions_doc_user"),
    )
    op.create_index(op.f("ix_document_permissions_id"), "document_permissions", ["id"], unique=False)
    op.create_index(op.f("ix_document_permissions_document_id"), "document_permissions", ["document_id"], unique=False)
    op.create_index(op.f("ix_document_permissions_user_id"), "document_permissions", ["user_id"], unique=False)
    op.create_index("ix_document_permissions_tenant_user", "document_permissions", ["tenant_id", "user_id"], unique=False)

    # 3. Create document_chunks table
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_tsv", TSVECTOR(), nullable=True),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("chunk_metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_chunks_id"), "document_chunks", ["id"], unique=False)
    op.create_index(op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"], unique=False)
    op.create_index(op.f("ix_document_chunks_tenant_id"), "document_chunks", ["tenant_id"], unique=False)
    op.create_index("ix_document_chunks_doc_chunk", "document_chunks", ["document_id", "chunk_index"], unique=False)
    op.create_index("ix_document_chunks_tsv", "document_chunks", ["content_tsv"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_document_chunks_tsv", table_name="document_chunks", postgresql_using="gin")
    op.drop_index("ix_document_chunks_doc_chunk", table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_tenant_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_id"), table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_document_permissions_tenant_user", table_name="document_permissions")
    op.drop_index(op.f("ix_document_permissions_user_id"), table_name="document_permissions")
    op.drop_index(op.f("ix_document_permissions_document_id"), table_name="document_permissions")
    op.drop_index(op.f("ix_document_permissions_id"), table_name="document_permissions")
    op.drop_table("document_permissions")

    op.drop_index("ix_documents_tenant_file_hash", table_name="documents")
    op.drop_index(op.f("ix_documents_owner_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_tenant_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_id"), table_name="documents")
    op.drop_table("documents")
