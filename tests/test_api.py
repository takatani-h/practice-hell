from pathlib import Path

import httpx
import pytest

from practice_hell.generator import FixedQuestionGenerator, GeneratedQuestion
from practice_hell.main import create_app


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(tmp_path: Path):
    app = create_app(
        database_path=tmp_path / "test.db",
        problems_directory=Path("problems"),
        generator=FixedQuestionGenerator(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client


async def join(client: httpx.AsyncClient, code: str) -> dict[str, str]:
    response = await client.post(
        "/api/sessions",
        json={"join_code": code, "student_number": "12", "student_name": "山田"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


async def test_number_answer_flow(client: httpx.AsyncClient) -> None:
    code = "20260715235000"
    exercise = await client.get(f"/api/exercises/{code}")
    assert exercise.status_code == 200
    assert exercise.json()["answer_type"] == "number"

    headers = await join(client, code)
    question = await client.get("/api/session/question", headers=headers)
    assert question.status_code == 200
    result = await client.post(
        "/api/session/answer",
        headers=headers,
        json={"question_id": question.json()["id"], "answer": "4"},
    )
    assert result.status_code == 200
    assert result.json()["correct"] is True
    assert result.json()["progress"]["total_answers"] == 1


async def test_single_choice_flow(client: httpx.AsyncClient) -> None:
    code = "20260716000206"
    headers = await join(client, code)
    question = (await client.get("/api/session/question", headers=headers)).json()
    assert len(question["choices"]) == 3
    result = await client.post(
        "/api/session/answer",
        headers=headers,
        json={"question_id": question["id"], "answer": "underdamped"},
    )
    assert result.status_code == 200
    assert result.json()["correct"] is True
    assert result.json()["correct_answer_label"] == "不足減衰"


async def test_mastery_uses_last_ten_answers(client: httpx.AsyncClient) -> None:
    headers = await join(client, "20260715235000")
    progress = None
    for index in range(10):
        question = (await client.get("/api/session/question", headers=headers)).json()
        answer = "4" if index < 8 else "0"
        result = await client.post(
            "/api/session/answer",
            headers=headers,
            json={"question_id": question["id"], "answer": answer},
        )
        assert result.status_code == 200
        progress = result.json()["progress"]
    assert progress is not None
    assert progress["recent_correct"] == 8
    assert progress["recent_accuracy_percent"] == 80.0
    assert progress["achieved"] is True


async def test_invalid_session_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/session/question", headers={"Authorization": "Bearer invalid"}
    )
    assert response.status_code == 401


async def test_blank_attendance_values_are_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/sessions",
        json={
            "join_code": "test-simple-addition",
            "student_number": "  ",
            "student_name": "山田",
        },
    )
    assert response.status_code == 422


class DelayedQuestionGenerator:
    def __init__(self) -> None:
        self.calls = 0
        self.available = False

    async def generate(self, problem, recent_question_texts, position):
        self.calls += 1
        if self.calls > 1 and not self.available:
            raise RuntimeError("次問を生成中")
        return GeneratedQuestion(
            question_text=f"確認問題 {position}: \\(2 + 2\\) を計算してください。",
            correct_answer="4",
        )


class RecordingQuestionGenerator:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(self, problem, recent_question_texts, position):
        prompt = problem.generation.prompt.strip()
        self.prompts.append(prompt)
        return GeneratedQuestion(question_text=prompt, correct_answer="4")


class SequentialQuestionGenerator:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, problem, recent_question_texts, position):
        self.calls += 1
        return GeneratedQuestion(
            question_text=f"生成問題 {self.calls}", correct_answer="4"
        )


async def test_next_question_status_waits_until_generation_finishes(
    tmp_path: Path,
) -> None:
    generator = DelayedQuestionGenerator()
    app = create_app(
        database_path=tmp_path / "delayed.db",
        problems_directory=Path("problems"),
        generator=generator,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as delayed_client:
        headers = await join(delayed_client, "test-simple-addition")
        question = (
            await delayed_client.get("/api/session/question", headers=headers)
        ).json()
        result = await delayed_client.post(
            "/api/session/answer",
            headers=headers,
            json={"question_id": question["id"], "answer": "4"},
        )
        assert result.status_code == 200
        assert result.json()["next_question_ready"] is False

        generator.available = True
        generating = await delayed_client.get(
            "/api/session/question-status", headers=headers
        )
        assert generating.json() == {"ready": False}
        ready = await delayed_client.get(
            "/api/session/question-status", headers=headers
        )
        assert ready.json() == {"ready": True}


async def test_updated_yaml_is_used_for_next_generation(tmp_path: Path) -> None:
    problem_directory = tmp_path / "problems"
    problem_directory.mkdir()
    source = Path("problems/example_simple_addition.yaml").read_text(encoding="utf-8")
    problem_path = problem_directory / "addition.yaml"
    problem_path.write_text(
        source.replace(
            "2つの数字X, Yについて、X + Yを計算する問題を1問作成する。",
            "変更前の条件で問題を作成する。",
        ),
        encoding="utf-8",
    )
    generator = RecordingQuestionGenerator()
    app = create_app(
        database_path=tmp_path / "reload.db",
        problems_directory=problem_directory,
        generator=generator,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as reload_client:
        headers = await join(reload_client, "test-simple-addition")
        assert len(generator.prompts) == 2
        assert all("変更前" in prompt for prompt in generator.prompts)

        problem_path.write_text(
            problem_path.read_text(encoding="utf-8").replace("変更前", "変更後"),
            encoding="utf-8",
        )

        first = (await reload_client.get(
            "/api/session/question", headers=headers
        )).json()
        await reload_client.post(
            "/api/session/answer",
            headers=headers,
            json={"question_id": first["id"], "answer": "4"},
        )
        second = (await reload_client.get(
            "/api/session/question", headers=headers
        )).json()
        await reload_client.post(
            "/api/session/answer",
            headers=headers,
            json={"question_id": second["id"], "answer": "4"},
        )
        third = (await reload_client.get(
            "/api/session/question", headers=headers
        )).json()

        assert "変更後" in generator.prompts[-1]
        assert "変更後" in third["question_text"]


async def test_regenerate_discards_buffered_question(tmp_path: Path) -> None:
    generator = SequentialQuestionGenerator()
    app = create_app(
        database_path=tmp_path / "regenerate.db",
        problems_directory=Path("problems"),
        generator=generator,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as regenerate_client:
        headers = await join(regenerate_client, "test-simple-addition")
        assert generator.calls == 2

        first = (await regenerate_client.get(
            "/api/session/question", headers=headers
        )).json()
        await regenerate_client.post(
            "/api/session/answer",
            headers=headers,
            json={"question_id": first["id"], "answer": "4"},
        )

        regenerated = await regenerate_client.post(
            "/api/session/question/regenerate", headers=headers
        )
        assert regenerated.status_code == 200
        assert regenerated.json() == {"ready": True}
        assert generator.calls == 3

        next_question = (await regenerate_client.get(
            "/api/session/question", headers=headers
        )).json()
        assert next_question["question_text"] == "生成問題 3"
