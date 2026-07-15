from __future__ import annotations

import os
from typing import Protocol

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from .config import NumberQuestion, ProblemConfig, SingleChoiceQuestion


class GeneratedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_text: str = Field(min_length=1)
    correct_answer: str = Field(min_length=1)


class QuestionGenerator(Protocol):
    async def generate(
        self, problem: ProblemConfig, recent_question_texts: list[str], position: int
    ) -> GeneratedQuestion: ...


class OpenAIQuestionGenerator:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-5.6")
        self.client: AsyncOpenAI | None = None

    async def generate(
        self, problem: ProblemConfig, recent_question_texts: list[str], position: int
    ) -> GeneratedQuestion:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEYが設定されていません")
        if isinstance(problem.question, NumberQuestion):
            output_rule = (
                "correct_answerは有限の10進数文字列にする。問題文に必要な単位を示すが、"
                "解答者には数値だけを入力させる。"
            )
        else:
            ids = ", ".join(choice.id for choice in problem.question.choices)
            output_rule = f"correct_answerは次の選択肢IDのいずれかにする: {ids}"

        recent = "\n\n".join(recent_question_texts[-5:]) or "なし"
        if self.client is None:
            self.client = AsyncOpenAI(api_key=self.api_key)
        response = await self.client.responses.parse(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "あなたは演習問題の作問者です。正答が一意に決まり、"
                        "問題文だけで解答できる問題を1問作成してください。"
                        "question_textには問題文だけを入れ、正答や解説は含めないでください。"
                        "数式はLaTeXで記述し、文中の数式を\\(...\\)、"
                        "独立した数式を\\[...\\]で囲んでください。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"作問条件:\n{problem.generation.prompt}\n\n"
                        f"出力条件:\n{output_rule}\n\n"
                        f"直近の問題（同じ問題を避ける）:\n{recent}"
                    ),
                },
            ],
            text_format=GeneratedQuestion,
        )
        generated = response.output_parsed
        if generated is None:
            raise RuntimeError("OpenAI APIが問題を返しませんでした")
        return validate_generated_question(problem, generated)


class FixedQuestionGenerator:
    """APIを使わないテスト・画面確認用ジェネレーター。"""

    async def generate(
        self, problem: ProblemConfig, recent_question_texts: list[str], position: int
    ) -> GeneratedQuestion:
        if isinstance(problem.question, NumberQuestion):
            return GeneratedQuestion(
                question_text=f"確認問題 {position}: 2 + 2 の値を答えてください。",
                correct_answer="4",
            )
        index = (position - 1) % len(problem.question.choices)
        choice = problem.question.choices[index]
        return GeneratedQuestion(
            question_text=(
                f"画面確認用問題 {position}: 「{choice.label}」を選んでください。"
            ),
            correct_answer=choice.id,
        )


def validate_generated_question(
    problem: ProblemConfig, generated: GeneratedQuestion
) -> GeneratedQuestion:
    if isinstance(problem.question, NumberQuestion):
        from decimal import Decimal, InvalidOperation

        try:
            answer = Decimal(generated.correct_answer)
        except InvalidOperation:
            raise ValueError("生成された数値正答が不正です") from None
        if not answer.is_finite():
            raise ValueError("生成された数値正答が有限値ではありません")
        generated.correct_answer = str(answer)
    elif isinstance(problem.question, SingleChoiceQuestion):
        valid_ids = {choice.id for choice in problem.question.choices}
        if generated.correct_answer not in valid_ids:
            raise ValueError("生成された正解が選択肢に含まれていません")
    return generated


def build_generator() -> QuestionGenerator:
    provider = os.getenv("QUESTION_PROVIDER", "openai")
    if provider == "fixed":
        return FixedQuestionGenerator()
    if provider == "openai":
        return OpenAIQuestionGenerator()
    raise RuntimeError(f"未対応のQUESTION_PROVIDERです: {provider}")
