import logging
from pathlib import Path

from practice_hell.generator import FixedQuestionGenerator
from practice_hell.main import create_app


def test_model_is_logged_once_when_app_is_created(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    create_app(
        database_path=tmp_path / "logging.db",
        problems_directory=Path("problems"),
        generator=FixedQuestionGenerator(),
    )

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("使用中のモデル:")
    ]
    assert messages == ["使用中のモデル: fixed"]
