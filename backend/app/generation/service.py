from app.generation.graph import GenerationTurn
from app.generation.graph import run_generation_session as run_checkpointed_session
from app.generation.persistence import open_postgres_checkpointer


def run_generation_session(
    member_id: str,
    coach_message: str,
    window: int,
    thread_id: str,
    message_id: str,
) -> GenerationTurn:
    with open_postgres_checkpointer() as checkpointer:
        return run_checkpointed_session(
            member_id,
            coach_message,
            window,
            thread_id,
            checkpointer=checkpointer,
            message_id=message_id,
        )
