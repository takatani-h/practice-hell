from decimal import Decimal

import httpx
import pytest

from backend.database import Base, engine
from backend.main import app
from backend.models import Question
from backend.service import is_correct


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client


async def login(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/teacher/login", json={"password": "change-me"})
    assert response.status_code == 200


async def create_exercise(client: httpx.AsyncClient, **overrides) -> dict:
    payload = {
        "title": "足し算",
        "generation_prompt": "1桁の足し算",
        "initial_count": 2,
        "refill_threshold": 1,
        "min_answers": 2,
        "ema_threshold": "1",
        "alpha": "1",
        "default_absolute_tolerance": "0",
        "default_relative_tolerance": "0",
    }
    payload.update(overrides)
    response = await client.post("/api/teacher/exercises", json=payload)
    assert response.status_code == 200
    return response.json()


async def test_teacher_authentication_is_required(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/teacher/exercises")).status_code == 401
    assert (await client.post("/api/teacher/login", json={"password": "wrong"})).status_code == 401


def test_numeric_tolerance_uses_larger_limit() -> None:
    question = Question(
        exercise_id=1,
        text="test",
        expected_answer="100",
        absolute_tolerance="0.5",
        relative_tolerance="0.01",
    )
    assert is_correct(Decimal("101"), question)
    assert not is_correct(Decimal("101.01"), question)


async def test_complete_exercise_flow(client: httpx.AsyncClient) -> None:
    await login(client)
    exercise = await create_exercise(client)

    generated = await client.post(f"/api/teacher/exercises/{exercise['id']}/generate")
    assert generated.status_code == 200
    detail = (await client.get(f"/api/teacher/exercises/{exercise['id']}")).json()
    assert len(detail["questions"]) == 2
    assert detail["jobs"][0]["status"] == "completed"

    for question in detail["questions"]:
        response = await client.patch(
            f"/api/teacher/questions/{question['id']}", json={"status": "approved"}
        )
        assert response.status_code == 200

    published = await client.post(f"/api/teacher/exercises/{exercise['id']}/publish")
    assert published.status_code == 200
    join_code = published.json()["join_code"]

    joined = await client.post(
        "/api/participant/join", json={"join_code": join_code, "display_name": "回答者A"}
    )
    assert joined.status_code == 200
    headers = {"Authorization": f"Bearer {joined.json()['token']}"}

    for expected_count in (1, 2):
        question = (await client.get("/api/participant/next", headers=headers)).json()["question"]
        detail = (await client.get(f"/api/teacher/exercises/{exercise['id']}")).json()
        expected = next(q["expected_answer"] for q in detail["questions"] if q["id"] == question["id"])
        answer = await client.post(
            "/api/participant/answer",
            headers=headers,
            json={"question_id": question["id"], "answer": expected},
        )
        assert answer.status_code == 200
        assert answer.json()["correct"] is True
        assert answer.json()["answer_count"] == expected_count

    assert answer.json()["achieved"] is True
    progress = (await client.get(f"/api/teacher/exercises/{exercise['id']}/progress")).json()
    assert progress[0]["display_name"] == "回答者A"
    assert progress[0]["achieved"] is True


@pytest.mark.parametrize("value", ["NaN", "Infinity", "abc", ""])
async def test_invalid_numeric_answers_are_rejected(
    client: httpx.AsyncClient, value: str
) -> None:
    await login(client)
    exercise = await create_exercise(client, initial_count=1)
    await client.post(f"/api/teacher/exercises/{exercise['id']}/generate")
    detail = (await client.get(f"/api/teacher/exercises/{exercise['id']}")).json()
    question = detail["questions"][0]
    await client.patch(f"/api/teacher/questions/{question['id']}", json={"status": "approved"})
    code = (await client.post(f"/api/teacher/exercises/{exercise['id']}/publish")).json()["join_code"]
    token = (await client.post(
        "/api/participant/join", json={"join_code": code, "display_name": "A"}
    )).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assigned = (await client.get("/api/participant/next", headers=headers)).json()["question"]
    response = await client.post(
        "/api/participant/answer",
        headers=headers,
        json={"question_id": assigned["id"], "answer": value},
    )
    assert response.status_code == 422
