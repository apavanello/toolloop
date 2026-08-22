from __future__ import annotations

import logging

import pytest

from toolloop import Agent, tool
from toolloop.devlog import LOGGER_NAME, dev_logger
from toolloop.testing import ScriptedProvider, final_answer, tool_call


@pytest.fixture(autouse=True)
def clean_toolloop_logger():
    logger = logging.getLogger(LOGGER_NAME)
    original_handlers = list(logger.handlers)
    logger.handlers.clear()
    yield
    logger.handlers.clear()
    logger.handlers.extend(original_handlers)


@tool
async def echo(text: str) -> str:
    """Echo the text."""
    return text


async def test_core_emits_step_tool_and_run_logs(caplog):
    provider = ScriptedProvider([tool_call("echo", call_id="c1", text="hi"), final_answer("done")])
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        result = await Agent(provider, tools=[echo]).run("x")

    assert result.output == "done"
    messages = [record.getMessage() for record in caplog.records]
    assert any("echo" in message and "ok" in message for message in messages)
    assert any("final_answer" in message for message in messages)
    assert any("run finished" in message and "completed" in message for message in messages)


async def test_parse_error_logs_warning(caplog):
    provider = ScriptedProvider(["not json at all", final_answer("ok")])
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        await Agent(provider, tools=[echo]).run("x")

    warnings = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING and "parse error" in record.getMessage()
    ]
    assert warnings


async def test_dev_logger_writes_to_file(tmp_path):
    path = tmp_path / "run.log"
    dev_logger(str(path))
    dev_logger(str(path))  # idempotent: handlers are replaced, not stacked
    assert len(logging.getLogger(LOGGER_NAME).handlers) == 1

    provider = ScriptedProvider([tool_call("echo", call_id="c1", text="hi"), final_answer("done")])
    await Agent(provider, tools=[echo]).run("x")

    for handler in logging.getLogger(LOGGER_NAME).handlers:
        handler.flush()
    content = path.read_text()
    assert "echo" in content
    assert "run finished" in content
    assert "WARNING" not in content  # INFO level by default
