from datetime import date

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
from app.copilot.persistence import open_postgres_checkpointer


def run_copilot_turn(
    member_id: str,
    message: str,
    *,
    message_id: str | None = None,
    as_of: date | None = None,
) -> CopilotTurn:
    with open_postgres_checkpointer() as checkpointer:
        return run_checkpointed_turn(
            member_id,
            message,
            checkpointer=checkpointer,
            message_id=message_id,
            as_of=as_of,
        )


def replay_copilot_history(
    member_id: str,
) -> tuple[CopilotHistoryMessage, ...]:
    with open_postgres_checkpointer() as checkpointer:
        return replay_checkpointed_history(member_id, checkpointer=checkpointer)
