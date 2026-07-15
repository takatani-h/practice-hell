from __future__ import annotations

import asyncio
import os
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .config import NumberQuestion, ProblemConfig, SingleChoiceQuestion, load_problems
from .generator import QuestionGenerator, build_generator
from .storage import Progress, Store


load_dotenv()
ROOT = Path(__file__).resolve().parent.parent


class SessionCreate(BaseModel):
    join_code: str
    student_number: str = Field(min_length=1, max_length=40)
    student_name: str = Field(min_length=1, max_length=100)

    @field_validator("student_number", "student_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("空白以外の文字を入力してください")
        return value


class AnswerSubmit(BaseModel):
    question_id: int
    answer: str = Field(min_length=1, max_length=200)


def progress_dict(progress: Progress) -> dict:
    return {
        "total_answers": progress.total_answers,
        "recent_answers": progress.recent_answers,
        "recent_correct": progress.recent_correct,
        "recent_accuracy_percent": round(progress.recent_accuracy_percent, 1),
        "window_size": progress.window_size,
        "required_accuracy_percent": progress.required_accuracy_percent,
        "achieved": progress.achieved,
    }


def exercise_dict(problem: ProblemConfig, model_name: str) -> dict:
    result = {
        "join_code": problem.join_code,
        "title": problem.title,
        "answer_type": problem.question.answer_type,
        "model": model_name,
        "mastery": problem.mastery.model_dump(),
    }
    if isinstance(problem.question, SingleChoiceQuestion):
        result["choices"] = [choice.model_dump() for choice in problem.question.choices]
    return result


def create_app(
    *,
    database_path: Path | None = None,
    problems_directory: Path | None = None,
    generator: QuestionGenerator | None = None,
) -> FastAPI:
    problems = load_problems(problems_directory or ROOT / "problems")
    store = Store(database_path or Path(os.getenv("DATABASE_PATH", "practice-hell.db")))
    question_generator = generator or build_generator()
    model_name = str(
        getattr(question_generator, "model_name", question_generator.__class__.__name__)
    )
    generation_locks: dict[int, asyncio.Lock] = {}

    app = FastAPI(title="PracticeHell", version="0.1.0")
    app.state.problems = problems
    app.state.store = store

    def problem_for_session(session: sqlite3.Row) -> ProblemConfig:
        problem = problems.get(str(session["join_code"]))
        if problem is None:
            raise HTTPException(404, "演習が見つかりません")
        return problem

    async def require_session(
        authorization: str | None = Header(default=None),
    ) -> sqlite3.Row:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "出席情報がありません")
        session = store.get_session(authorization[7:])
        if session is None:
            raise HTTPException(401, "出席情報が無効です")
        return session

    async def generate_one(session_id: int, problem: ProblemConfig) -> None:
        reserved = store.reserve_question(session_id, problem.question.answer_type)
        try:
            generated = await question_generator.generate(
                problem,
                store.recent_question_texts(session_id),
                int(reserved["position"]),
            )
            store.complete_question(
                int(reserved["id"]), generated.question_text, generated.correct_answer
            )
        except Exception as exc:
            store.fail_question(int(reserved["id"]), str(exc))
            raise

    async def ensure_buffer(
        session_id: int, problem: ProblemConfig, target: int, raise_errors: bool = False
    ) -> None:
        lock = generation_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            while store.count_buffered_questions(session_id) < target:
                try:
                    await generate_one(session_id, problem)
                except Exception:
                    if raise_errors:
                        raise
                    return

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/exercises/{join_code}")
    async def get_exercise(join_code: str) -> dict:
        problem = problems.get(join_code)
        if problem is None:
            raise HTTPException(404, "参加コードに対応する演習がありません")
        return exercise_dict(problem, model_name)

    @app.post("/api/sessions")
    async def create_session(
        payload: SessionCreate, background_tasks: BackgroundTasks
    ) -> dict:
        problem = problems.get(payload.join_code)
        if problem is None:
            raise HTTPException(404, "参加コードに対応する演習がありません")
        session_id, token = store.create_session(
            payload.join_code,
            payload.student_number,
            payload.student_name,
        )
        try:
            await ensure_buffer(session_id, problem, target=1, raise_errors=True)
        except Exception as exc:
            raise HTTPException(503, f"最初の問題を生成できませんでした: {exc}") from exc
        background_tasks.add_task(ensure_buffer, session_id, problem, 2)
        return {"token": token, "exercise": exercise_dict(problem, model_name)}

    @app.get("/api/session/question")
    async def get_question(
        background_tasks: BackgroundTasks,
        session: sqlite3.Row = Depends(require_session),
    ) -> dict:
        problem = problem_for_session(session)
        question = store.claim_question(int(session["id"]))
        if question is None:
            await ensure_buffer(int(session["id"]), problem, target=1)
            question = store.claim_question(int(session["id"]))
        if question is None:
            raise HTTPException(503, "問題を生成できませんでした。再試行してください")
        background_tasks.add_task(ensure_buffer, int(session["id"]), problem, 1)
        result = {
            "id": question["id"],
            "question_text": question["question_text"],
            "answer_type": question["answer_type"],
        }
        if isinstance(problem.question, SingleChoiceQuestion):
            result["choices"] = [choice.model_dump() for choice in problem.question.choices]
        return result

    @app.get("/api/session/question-status")
    async def get_question_status(
        background_tasks: BackgroundTasks,
        session: sqlite3.Row = Depends(require_session),
    ) -> dict:
        problem = problem_for_session(session)
        ready = store.has_ready_question(int(session["id"]))
        if not ready:
            background_tasks.add_task(ensure_buffer, int(session["id"]), problem, 1)
        return {"ready": ready}

    @app.post("/api/session/answer")
    async def submit_answer(
        payload: AnswerSubmit,
        background_tasks: BackgroundTasks,
        session: sqlite3.Row = Depends(require_session),
    ) -> dict:
        problem = problem_for_session(session)
        question = store.get_question(payload.question_id)
        if (
            question is None
            or int(question["session_id"]) != int(session["id"])
            or question["status"] != "presented"
        ):
            raise HTTPException(409, "現在出題中の問題ではありません")

        submitted = payload.answer.strip()
        if isinstance(problem.question, NumberQuestion):
            try:
                submitted_number = Decimal(submitted)
                expected = Decimal(str(question["correct_answer"]))
            except InvalidOperation:
                raise HTTPException(422, "有効な数値を入力してください") from None
            if not submitted_number.is_finite():
                raise HTTPException(422, "有限の数値を入力してください")
            absolute = Decimal(problem.question.absolute_tolerance)
            relative = Decimal(problem.question.relative_tolerance) * abs(expected)
            correct = abs(submitted_number - expected) <= max(absolute, relative)
            correct_answer_label = str(question["correct_answer"])
        else:
            choices = {choice.id: choice.label for choice in problem.question.choices}
            if submitted not in choices:
                raise HTTPException(422, "選択肢を1つ選んでください")
            correct = submitted == question["correct_answer"]
            correct_answer_label = choices[str(question["correct_answer"])]

        try:
            store.save_answer(
                int(session["id"]), int(question["id"]), submitted, correct
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "この問題には解答済みです") from exc

        progress = store.progress(
            int(session["id"]),
            problem.mastery.window_size,
            problem.mastery.required_accuracy_percent,
        )
        store.save_progress_snapshot(int(question["id"]), progress)
        background_tasks.add_task(ensure_buffer, int(session["id"]), problem, 1)
        return {
            "correct": correct,
            "correct_answer": str(question["correct_answer"]),
            "correct_answer_label": correct_answer_label,
            "progress": progress_dict(progress),
            "next_question_ready": store.has_ready_question(int(session["id"])),
        }

    dist = ROOT / "dist"
    if dist.exists():
        assets = dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            return FileResponse(dist / "index.html")

    return app
