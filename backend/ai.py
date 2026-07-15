from __future__ import annotations

import json
from typing import Protocol

import httpx

from .config import Settings
from .schemas import GeneratedQuestion, GeneratedQuestionList


class QuestionGenerator(Protocol):
    async def generate(
        self, prompt: str, count: int, absolute_tolerance: str, relative_tolerance: str
    ) -> list[GeneratedQuestion]: ...


class MockQuestionGenerator:
    async def generate(
        self, prompt: str, count: int, absolute_tolerance: str, relative_tolerance: str
    ) -> list[GeneratedQuestion]:
        return [
            GeneratedQuestion(
                text=f"{prompt}\n練習問題 {index + 1}: {index + 1} + {index + 1} は？",
                expected_answer=str((index + 1) * 2),
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
            for index in range(count)
        ]


class OpenAICompatibleGenerator:
    def __init__(self, settings: Settings) -> None:
        if not settings.llm_api_key or not settings.llm_model:
            raise RuntimeError("LLM_API_KEY と LLM_MODEL を設定してください")
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    async def generate(
        self, prompt: str, count: int, absolute_tolerance: str, relative_tolerance: str
    ) -> list[GeneratedQuestion]:
        schema = GeneratedQuestionList.model_json_schema()
        request = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "あなたは数値解答式の練習問題を作る。問題文だけで正答が一意に決まり、"
                        "expected_answer と許容誤差は有限かつ非負の10進数文字列にする。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"次の条件で重複しない問題を{count}問生成してください。\n{prompt}\n"
                        f"既定の絶対許容誤差: {absolute_tolerance}\n"
                        f"既定の相対許容誤差: {relative_tolerance}"
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "generated_questions", "strict": True, "schema": schema},
            },
        }
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=request,
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        result = GeneratedQuestionList.model_validate(json.loads(content))
        if len(result.questions) != count:
            raise ValueError(f"AIが{count}問ではなく{len(result.questions)}問を返しました")
        return result.questions


def build_generator(settings: Settings) -> QuestionGenerator:
    if settings.llm_provider == "mock":
        return MockQuestionGenerator()
    if settings.llm_provider == "openai-compatible":
        return OpenAICompatibleGenerator(settings)
    raise RuntimeError(f"未対応の LLM_PROVIDER です: {settings.llm_provider}")
