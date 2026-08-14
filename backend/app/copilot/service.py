from datetime import date
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.copilot.agent import (
    CopilotHistoryMessage,
    CopilotTurn,
)
from app.copilot.agent import (
    replay_copilot_history as replay_checkpointed_history,
)
from app.copilot.agent import (
    run_copilot_turn as run_checkpointed_turn,
)
from app.copilot.llm import CopilotLLM
from app.copilot.persistence import open_postgres_checkpointer


def run_copilot_turn(
    member_id: str,
    message: str,
    *,
    message_id: str | None = None,
    as_of: date | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    llm: CopilotLLM | None = None,
) -> CopilotTurn:
    if checkpointer is not None:
        return run_checkpointed_turn(
            member_id,
            message,
            checkpointer=checkpointer,
            llm=llm,
            message_id=message_id,
            as_of=as_of,
        )
    with open_postgres_checkpointer() as production_checkpointer:
        return run_checkpointed_turn(
            member_id,
            message,
            checkpointer=production_checkpointer,
            llm=llm,
            message_id=message_id,
            as_of=as_of,
        )


def replay_copilot_history(
    member_id: str,
) -> tuple[CopilotHistoryMessage, ...]:
    with open_postgres_checkpointer() as checkpointer:
        return replay_checkpointed_history(member_id, checkpointer=checkpointer)
