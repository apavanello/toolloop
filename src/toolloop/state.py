"""Session persistence: serializable snapshots of an agent conversation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ._types import Message, Role, StepRecord, ToolCallRecord

STATE_VERSION = 1


@dataclass
class AgentState:
    """A serializable snapshot of an agent's conversation and audit trail.

    Configuration (provider, tools, hooks) is code and is NOT part of the
    state — rebuild it with ``Agent.from_state(state, provider, tools=...)``.
    If the tool set changed between save and resume, the mismatch with the
    system prompt already stored in ``messages`` is your responsibility.
    """

    version: int = STATE_VERSION
    messages: list[Message] = field(default_factory=list)
    history: list[StepRecord] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": self.version,
                "created_at": self.created_at,
                "messages": [
                    {"role": m.role.value, "content": m.content, "kind": m.kind}
                    for m in self.messages
                ],
                "history": [_dump_record(record) for record in self.history],
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> AgentState:
        data = json.loads(raw)
        version = data.get("version", STATE_VERSION)
        if version != STATE_VERSION:
            raise ValueError(f"unsupported AgentState version: {version!r}")
        return cls(
            version=version,
            messages=[
                Message(role=Role(m["role"]), content=m["content"], kind=m.get("kind"))
                for m in data.get("messages", [])
            ],
            history=[_load_record(record) for record in data.get("history", [])],
            created_at=data.get("created_at", ""),
        )


def _dump_record(record: StepRecord) -> dict[str, Any]:
    return {
        "step": record.step,
        "raw": record.raw,
        "kind": record.kind,
        "calls": [
            {
                "call_id": call.call_id,
                "name": call.name,
                "args": call.args,
                "status": call.status,
                "result": call.result,
                "duration": call.duration,
            }
            for call in record.calls
        ],
    }


def _load_record(data: dict[str, Any]) -> StepRecord:
    return StepRecord(
        step=data["step"],
        raw=data["raw"],
        kind=data["kind"],
        calls=[
            ToolCallRecord(
                call_id=call["call_id"],
                name=call["name"],
                args=call["args"],
                status=call["status"],
                result=call["result"],
                duration=call.get("duration", 0.0),
            )
            for call in data.get("calls", [])
        ],
    )
