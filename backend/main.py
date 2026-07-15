from __future__ import annotations

import hmac
from decimal import Decimal
from pathlib import Path

from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ai import build_generator
from .auth import hash_token, make_teacher_token, new_participant_token, verify_teacher_token
from .config import Settings
from .database import SessionLocal, get_db
from .models import Answer, Exercise, GenerationJob, Participant, Question
from .schemas import ExerciseCreate, JoinRequest, QuestionUpdate, SubmitAnswer, TeacherLogin
from .service import create_join_code, is_correct, next_question, parse_decimal, update_progress


def exercise_dict(exercise: Exercise) -> dict:
    return {
        "id": exercise.id,
        "title": exercise.title,
        "generation_prompt": exercise.generation_prompt,
        "status": exercise.status,
        "join_code": exercise.join_code,
        "initial_count": exercise.initial_count,
        "refill_threshold": exercise.refill_threshold,
        "min_answers": exercise.min_answers,
        "ema_threshold": exercise.ema_threshold,
        "alpha": exercise.alpha,
        "default_absolute_tolerance": exercise.default_absolute_tolerance,
        "default_relative_tolerance": exercise.default_relative_tolerance,
    }


def question_dict(question: Question, include_answer: bool = True) -> dict:
    result = {"id": question.id, "text": question.text, "status": question.status}
    if include_answer:
        result.update(
            expected_answer=question.expected_answer,
            absolute_tolerance=question.absolute_tolerance,
            relative_tolerance=question.relative_tolerance,
        )
    return result


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()
    app = FastAPI(title="PracticeHell", version="0.1.0")
    app.state.settings = app_settings

    async def require_teacher(teacher_session: str | None = Cookie(default=None)) -> None:
        if not verify_teacher_token(teacher_session, app.state.settings.session_secret):
            raise HTTPException(401, "教師としてログインしてください")

    async def require_participant(
        authorization: str | None = Header(default=None),
        db: Session = Depends(get_db),
    ) -> Participant:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "参加情報がありません")
        participant = db.scalar(
            select(Participant).where(Participant.token_hash == hash_token(authorization[7:]))
        )
        if participant is None:
            raise HTTPException(401, "参加情報が無効です")
        return participant

    async def run_generation(job_id: int) -> None:
        with SessionLocal() as db:
            job = db.get(GenerationJob, job_id)
            if job is None:
                return
            exercise = db.get(Exercise, job.exercise_id)
            if exercise is None:
                return
            job.status = "running"
            db.commit()
            try:
                generated = await build_generator(app.state.settings).generate(
                    exercise.generation_prompt,
                    job.requested_count,
                    exercise.default_absolute_tolerance,
                    exercise.default_relative_tolerance,
                )
                for item in generated:
                    absolute = parse_decimal(item.absolute_tolerance)
                    relative = parse_decimal(item.relative_tolerance)
                    if absolute < 0 or relative < 0:
                        raise ValueError("許容誤差は0以上にしてください")
                    db.add(
                        Question(
                            exercise_id=exercise.id,
                            text=item.text,
                            expected_answer=str(parse_decimal(item.expected_answer)),
                            absolute_tolerance=str(absolute),
                            relative_tolerance=str(relative),
                        )
                    )
                job.status = "completed"
                job.error = None
            except Exception as exc:  # generation failures must remain visible and retryable
                job.status = "failed"
                job.error = str(exc)[:2000]
            db.commit()

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/teacher/login")
    async def teacher_login(payload: TeacherLogin, response: Response) -> dict:
        if not hmac.compare_digest(payload.password, app.state.settings.teacher_password):
            raise HTTPException(401, "パスワードが違います")
        response.set_cookie(
            "teacher_session",
            make_teacher_token(app.state.settings.session_secret),
            httponly=True,
            secure=app.state.settings.cookie_secure,
            samesite="lax",
            max_age=43_200,
        )
        return {"ok": True}

    @app.post("/api/teacher/logout")
    async def teacher_logout(response: Response) -> dict:
        response.delete_cookie("teacher_session")
        return {"ok": True}

    @app.get("/api/teacher/exercises", dependencies=[Depends(require_teacher)])
    async def list_exercises(db: Session = Depends(get_db)) -> list[dict]:
        exercises = db.scalars(select(Exercise).order_by(Exercise.id.desc())).all()
        return [exercise_dict(exercise) for exercise in exercises]

    @app.post("/api/teacher/exercises", dependencies=[Depends(require_teacher)])
    async def create_exercise(payload: ExerciseCreate, db: Session = Depends(get_db)) -> dict:
        try:
            alpha = parse_decimal(payload.alpha)
            threshold = parse_decimal(payload.ema_threshold)
            absolute = parse_decimal(payload.default_absolute_tolerance)
            relative = parse_decimal(payload.default_relative_tolerance)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not Decimal(0) < alpha <= Decimal(1):
            raise HTTPException(422, "αは0より大きく1以下にしてください")
        if not Decimal(0) <= threshold <= Decimal(1):
            raise HTTPException(422, "EMA閾値は0以上1以下にしてください")
        if absolute < 0 or relative < 0:
            raise HTTPException(422, "許容誤差は0以上にしてください")
        exercise = Exercise(
            **payload.model_dump(exclude={"alpha", "ema_threshold", "default_absolute_tolerance", "default_relative_tolerance"}),
            alpha=str(alpha),
            ema_threshold=str(threshold),
            default_absolute_tolerance=str(absolute),
            default_relative_tolerance=str(relative),
        )
        db.add(exercise)
        db.commit()
        return exercise_dict(exercise)

    @app.get("/api/teacher/exercises/{exercise_id}", dependencies=[Depends(require_teacher)])
    async def get_exercise(exercise_id: int, db: Session = Depends(get_db)) -> dict:
        exercise = db.get(Exercise, exercise_id)
        if exercise is None:
            raise HTTPException(404, "演習が見つかりません")
        result = exercise_dict(exercise)
        result["questions"] = [question_dict(question) for question in exercise.questions]
        result["jobs"] = [
            {"id": job.id, "status": job.status, "error": job.error, "requested_count": job.requested_count}
            for job in db.scalars(
                select(GenerationJob)
                .where(GenerationJob.exercise_id == exercise.id)
                .order_by(GenerationJob.id.desc())
            )
        ]
        return result

    @app.post("/api/teacher/exercises/{exercise_id}/generate", dependencies=[Depends(require_teacher)])
    async def generate_questions(
        exercise_id: int,
        background_tasks: BackgroundTasks,
        count: int | None = None,
        db: Session = Depends(get_db),
    ) -> dict:
        exercise = db.get(Exercise, exercise_id)
        if exercise is None:
            raise HTTPException(404, "演習が見つかりません")
        requested_count = count or exercise.initial_count
        if not 1 <= requested_count <= 100:
            raise HTTPException(422, "生成数は1〜100問にしてください")
        job = GenerationJob(exercise_id=exercise.id, requested_count=requested_count)
        db.add(job)
        db.commit()
        background_tasks.add_task(run_generation, job.id)
        return {"job_id": job.id, "status": job.status}

    @app.patch("/api/teacher/questions/{question_id}", dependencies=[Depends(require_teacher)])
    async def update_question(question_id: int, payload: QuestionUpdate, db: Session = Depends(get_db)) -> dict:
        question = db.get(Question, question_id)
        if question is None:
            raise HTTPException(404, "問題が見つかりません")
        changes = payload.model_dump(exclude_none=True)
        if "status" in changes and changes["status"] not in {"pending", "approved", "rejected"}:
            raise HTTPException(422, "問題の状態が不正です")
        try:
            for field in ("expected_answer", "absolute_tolerance", "relative_tolerance"):
                if field in changes:
                    changes[field] = str(parse_decimal(changes[field]))
            if parse_decimal(changes.get("absolute_tolerance", question.absolute_tolerance)) < 0:
                raise ValueError("許容誤差は0以上にしてください")
            if parse_decimal(changes.get("relative_tolerance", question.relative_tolerance)) < 0:
                raise ValueError("許容誤差は0以上にしてください")
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        for key, value in changes.items():
            setattr(question, key, value)
        db.commit()
        return question_dict(question)

    @app.post("/api/teacher/exercises/{exercise_id}/publish", dependencies=[Depends(require_teacher)])
    async def publish_exercise(exercise_id: int, db: Session = Depends(get_db)) -> dict:
        exercise = db.get(Exercise, exercise_id)
        if exercise is None:
            raise HTTPException(404, "演習が見つかりません")
        approved = db.scalar(
            select(func.count()).select_from(Question).where(
                Question.exercise_id == exercise.id, Question.status == "approved"
            )
        )
        if not approved:
            raise HTTPException(409, "承認済みの問題が必要です")
        exercise.status = "published"
        exercise.join_code = exercise.join_code or create_join_code(db)
        db.commit()
        return exercise_dict(exercise)

    @app.post("/api/teacher/exercises/{exercise_id}/close", dependencies=[Depends(require_teacher)])
    async def close_exercise(exercise_id: int, db: Session = Depends(get_db)) -> dict:
        exercise = db.get(Exercise, exercise_id)
        if exercise is None:
            raise HTTPException(404, "演習が見つかりません")
        exercise.status = "closed"
        db.commit()
        return exercise_dict(exercise)

    @app.get("/api/teacher/exercises/{exercise_id}/progress", dependencies=[Depends(require_teacher)])
    async def exercise_progress(exercise_id: int, db: Session = Depends(get_db)) -> list[dict]:
        participants = db.scalars(
            select(Participant).where(Participant.exercise_id == exercise_id).order_by(Participant.id)
        ).all()
        return [
            {
                "id": item.id,
                "display_name": item.display_name,
                "answer_count": item.answer_count,
                "ema": item.ema,
                "achieved": item.achieved,
            }
            for item in participants
        ]

    @app.post("/api/participant/join")
    async def join(payload: JoinRequest, db: Session = Depends(get_db)) -> dict:
        exercise = db.scalar(
            select(Exercise).where(
                Exercise.join_code == payload.join_code.strip().upper(),
                Exercise.status == "published",
            )
        )
        if exercise is None:
            raise HTTPException(404, "公開中の演習が見つかりません")
        token = new_participant_token()
        participant = Participant(
            exercise_id=exercise.id,
            display_name=payload.display_name.strip(),
            token_hash=hash_token(token),
        )
        db.add(participant)
        db.commit()
        return {
            "token": token,
            "exercise": {"title": exercise.title, "min_answers": exercise.min_answers, "ema_threshold": exercise.ema_threshold},
        }

    @app.get("/api/participant/next")
    async def get_next_question(
        background_tasks: BackgroundTasks,
        participant: Participant = Depends(require_participant),
        db: Session = Depends(get_db),
    ) -> dict:
        if participant.exercise.status != "published":
            raise HTTPException(409, "この演習は終了しています")
        question = next_question(db, participant)
        participant.current_question_id = question.id
        unseen_count = db.scalar(
            select(func.count()).select_from(Question).where(
                Question.exercise_id == participant.exercise_id,
                Question.status == "approved",
                Question.id.not_in(
                    select(Answer.question_id).where(Answer.participant_id == participant.id)
                ),
            )
        ) or 0
        active_job = db.scalar(
            select(GenerationJob).where(
                GenerationJob.exercise_id == participant.exercise_id,
                GenerationJob.status.in_(["queued", "running"]),
            )
        )
        if unseen_count <= participant.exercise.refill_threshold and active_job is None:
            job = GenerationJob(
                exercise_id=participant.exercise_id,
                requested_count=participant.exercise.refill_threshold,
            )
            db.add(job)
            db.commit()
            background_tasks.add_task(run_generation, job.id)
        else:
            db.commit()
        return {"question": question_dict(question, include_answer=False)}

    @app.post("/api/participant/answer")
    async def submit_answer(
        payload: SubmitAnswer,
        participant: Participant = Depends(require_participant),
        db: Session = Depends(get_db),
    ) -> dict:
        question = db.get(Question, payload.question_id)
        if (
            question is None
            or question.exercise_id != participant.exercise_id
            or question.status != "approved"
            or participant.current_question_id != question.id
        ):
            raise HTTPException(404, "出題された問題が見つかりません")
        try:
            submitted = parse_decimal(payload.answer)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        correct = is_correct(submitted, question)
        db.add(
            Answer(
                participant_id=participant.id,
                question_id=question.id,
                submitted_answer=str(submitted),
                correct=correct,
            )
        )
        update_progress(participant, correct)
        participant.current_question_id = None
        db.commit()
        return {
            "correct": correct,
            "expected_answer": question.expected_answer,
            "answer_count": participant.answer_count,
            "ema": participant.ema,
            "achieved": participant.achieved,
        }

    dist = Path(__file__).resolve().parent.parent / "dist"
    if dist.exists():
        assets = dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            return FileResponse(dist / "index.html")

    return app


app = create_app()
