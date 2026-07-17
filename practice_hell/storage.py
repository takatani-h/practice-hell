from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Progress:
    total_answers: int
    recent_answers: int
    recent_correct: int
    recent_accuracy_percent: float
    window_size: int
    required_accuracy_percent: int
    achieved: bool


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    join_code TEXT NOT NULL,
                    student_number TEXT NOT NULL,
                    student_name TEXT NOT NULL,
                    achieved INTEGER NOT NULL DEFAULT 0,
                    achieved_at TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY,
                    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    question_text TEXT,
                    answer_type TEXT NOT NULL,
                    correct_answer TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, position)
                );

                CREATE TABLE IF NOT EXISTS answers (
                    id INTEGER PRIMARY KEY,
                    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    question_id INTEGER NOT NULL UNIQUE REFERENCES questions(id) ON DELETE CASCADE,
                    submitted_answer TEXT NOT NULL,
                    correct INTEGER NOT NULL,
                    total_answers INTEGER,
                    recent_answers INTEGER,
                    recent_correct INTEGER,
                    recent_accuracy_percent REAL,
                    achieved INTEGER,
                    answered_at TEXT NOT NULL
                );
                """
            )
            existing_columns = {
                str(row[1]) for row in db.execute("PRAGMA table_info(answers)").fetchall()
            }
            for name, sql_type in {
                "total_answers": "INTEGER",
                "recent_answers": "INTEGER",
                "recent_correct": "INTEGER",
                "recent_accuracy_percent": "REAL",
                "achieved": "INTEGER",
            }.items():
                if name not in existing_columns:
                    db.execute(f"ALTER TABLE answers ADD COLUMN {name} {sql_type}")

    def create_session(
        self, join_code: str, student_number: str, student_name: str
    ) -> tuple[int, str]:
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO sessions
                    (token_hash, join_code, student_number, student_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token_hash(token), join_code, student_number, student_name, utc_now()),
            )
            return int(cursor.lastrowid), token

    def get_session(self, token: str) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM sessions WHERE token_hash=?", (token_hash(token),)
            ).fetchone()

    def reserve_question(self, session_id: int, answer_type: str) -> sqlite3.Row:
        with self.connect() as db:
            position = db.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM questions WHERE session_id=?",
                (session_id,),
            ).fetchone()[0]
            cursor = db.execute(
                """
                INSERT INTO questions
                    (session_id, position, answer_type, status, created_at)
                VALUES (?, ?, ?, 'generating', ?)
                """,
                (session_id, position, answer_type, utc_now()),
            )
            return db.execute(
                "SELECT * FROM questions WHERE id=?", (cursor.lastrowid,)
            ).fetchone()

    def complete_question(
        self, question_id: int, question_text: str, correct_answer: str
    ) -> None:
        with self.connect() as db:
            db.execute(
                """
                UPDATE questions
                SET question_text=?, correct_answer=?, status='ready', error=NULL
                WHERE id=?
                """,
                (question_text, correct_answer, question_id),
            )

    def fail_question(self, question_id: int, error: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE questions SET status='failed', error=? WHERE id=?",
                (error[:1000], question_id),
            )

    def count_buffered_questions(self, session_id: int) -> int:
        with self.connect() as db:
            return int(
                db.execute(
                    """
                    SELECT COUNT(*) FROM questions
                    WHERE session_id=? AND status IN ('ready', 'generating')
                    """,
                    (session_id,),
                ).fetchone()[0]
            )

    def has_ready_question(self, session_id: int) -> bool:
        with self.connect() as db:
            return (
                db.execute(
                    """
                    SELECT 1 FROM questions
                    WHERE session_id=? AND status='ready'
                    LIMIT 1
                    """,
                    (session_id,),
                ).fetchone()
                is not None
            )

    def discard_buffered_questions(self, session_id: int) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """
                DELETE FROM questions
                WHERE session_id=? AND status IN ('ready', 'generating')
                """,
                (session_id,),
            )
            return cursor.rowcount

    def recent_question_texts(self, session_id: int, limit: int = 5) -> list[str]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT question_text FROM questions
                WHERE session_id=? AND question_text IS NOT NULL
                ORDER BY position DESC LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
            return [str(row[0]) for row in rows]

    def claim_question(self, session_id: int) -> sqlite3.Row | None:
        with self.connect() as db:
            current = db.execute(
                """
                SELECT * FROM questions
                WHERE session_id=? AND status='presented'
                ORDER BY position LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if current:
                return current
            ready = db.execute(
                """
                SELECT * FROM questions
                WHERE session_id=? AND status='ready'
                ORDER BY position LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if ready is None:
                return None
            db.execute("UPDATE questions SET status='presented' WHERE id=?", (ready["id"],))
            return db.execute("SELECT * FROM questions WHERE id=?", (ready["id"],)).fetchone()

    def get_question(self, question_id: int) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute("SELECT * FROM questions WHERE id=?", (question_id,)).fetchone()

    def save_answer(
        self, session_id: int, question_id: int, submitted_answer: str, correct: bool
    ) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO answers
                    (session_id, question_id, submitted_answer, correct, answered_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, question_id, submitted_answer, int(correct), utc_now()),
            )
            db.execute("UPDATE questions SET status='answered' WHERE id=?", (question_id,))

    def progress(
        self, session_id: int, window_size: int, required_accuracy_percent: int
    ) -> Progress:
        with self.connect() as db:
            total = int(
                db.execute(
                    "SELECT COUNT(*) FROM answers WHERE session_id=?", (session_id,)
                ).fetchone()[0]
            )
            recent = db.execute(
                """
                SELECT correct FROM answers
                WHERE session_id=? ORDER BY id DESC LIMIT ?
                """,
                (session_id, window_size),
            ).fetchall()
            correct_count = sum(int(row[0]) for row in recent)
            recent_count = len(recent)
            accuracy = correct_count * 100 / recent_count if recent_count else 0.0
            achieved_now = (
                recent_count == window_size
                and correct_count * 100 >= required_accuracy_percent * window_size
            )
            session = db.execute(
                "SELECT achieved FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            achieved = bool(session[0]) or achieved_now
            if achieved_now and not bool(session[0]):
                db.execute(
                    "UPDATE sessions SET achieved=1, achieved_at=? WHERE id=?",
                    (utc_now(), session_id),
                )
            return Progress(
                total_answers=total,
                recent_answers=recent_count,
                recent_correct=correct_count,
                recent_accuracy_percent=accuracy,
                window_size=window_size,
                required_accuracy_percent=required_accuracy_percent,
                achieved=achieved,
            )

    def save_progress_snapshot(self, question_id: int, progress: Progress) -> None:
        with self.connect() as db:
            db.execute(
                """
                UPDATE answers
                SET total_answers=?, recent_answers=?, recent_correct=?,
                    recent_accuracy_percent=?, achieved=?
                WHERE question_id=?
                """,
                (
                    progress.total_answers,
                    progress.recent_answers,
                    progress.recent_correct,
                    progress.recent_accuracy_percent,
                    int(progress.achieved),
                    question_id,
                ),
            )
