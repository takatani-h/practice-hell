"""初期スキーマ

Revision ID: 0001
Revises:
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("generation_prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("join_code", sa.String(12)),
        sa.Column("initial_count", sa.Integer(), nullable=False),
        sa.Column("refill_threshold", sa.Integer(), nullable=False),
        sa.Column("min_answers", sa.Integer(), nullable=False),
        sa.Column("ema_threshold", sa.String(40), nullable=False),
        sa.Column("alpha", sa.String(40), nullable=False),
        sa.Column("default_absolute_tolerance", sa.String(40), nullable=False),
        sa.Column("default_relative_tolerance", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("join_code"),
    )
    op.create_index("ix_exercises_status", "exercises", ["status"])
    op.create_index("ix_exercises_join_code", "exercises", ["join_code"], unique=True)
    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "exercise_id",
            sa.Integer(),
            sa.ForeignKey("exercises.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.String(100), nullable=False),
        sa.Column("absolute_tolerance", sa.String(40), nullable=False),
        sa.Column("relative_tolerance", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_questions_exercise_id", "questions", ["exercise_id"])
    op.create_index("ix_questions_status", "questions", ["status"])
    op.create_table(
        "participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "exercise_id",
            sa.Integer(),
            sa.ForeignKey("exercises.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "current_question_id",
            sa.Integer(),
            sa.ForeignKey("questions.id", ondelete="SET NULL"),
        ),
        sa.Column("answer_count", sa.Integer(), nullable=False),
        sa.Column("ema", sa.String(40)),
        sa.Column("achieved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_participants_exercise_id", "participants", ["exercise_id"])
    op.create_index("ix_participants_token_hash", "participants", ["token_hash"], unique=True)
    op.create_table(
        "answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.Integer(),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("submitted_answer", sa.String(100), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_answers_participant_id", "answers", ["participant_id"])
    op.create_index("ix_answers_question_id", "answers", ["question_id"])
    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "exercise_id",
            sa.Integer(),
            sa.ForeignKey("exercises.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_generation_jobs_exercise_id", "generation_jobs", ["exercise_id"])
    op.create_index("ix_generation_jobs_status", "generation_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("generation_jobs")
    op.drop_table("answers")
    op.drop_table("participants")
    op.drop_table("questions")
    op.drop_table("exercises")
