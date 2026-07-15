from pathlib import Path

import pytest

from practice_hell.config import load_problems


def test_all_problem_yamls_are_valid() -> None:
    problems = load_problems(Path("problems"))
    assert len(problems) == 3
    assert {problem.question.answer_type for problem in problems.values()} == {
        "number",
        "single_choice",
    }


def test_duplicate_join_code_is_rejected(tmp_path: Path) -> None:
    source = Path("problems/example_number_answer.yaml").read_text()
    (tmp_path / "one.yaml").write_text(source)
    (tmp_path / "two.yaml").write_text(source)
    with pytest.raises(RuntimeError, match="重複"):
        load_problems(tmp_path)
