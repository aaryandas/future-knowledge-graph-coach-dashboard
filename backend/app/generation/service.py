from app.generation._trace import AgentTraceEvent, TraceEvent
from app.generation.graph import GenerationTurn, append_annotation_trace_event
from app.generation.graph import run_generation_session as run_checkpointed_session
from app.generation.persistence import open_postgres_checkpointer


def run_generation_session(
    member_id: str,
    coach_message: str,
    window: int,
    thread_id: str,
    message_id: str,
) -> GenerationTurn:
    def record_annotation_trace(
        trace: tuple[TraceEvent, ...],
        event: AgentTraceEvent,
    ) -> None:
        with open_postgres_checkpointer() as checkpointer:
            append_annotation_trace_event(
                thread_id,
                trace,
                event,
                checkpointer=checkpointer,
            )

    with open_postgres_checkpointer() as checkpointer:
        return run_checkpointed_session(
            member_id,
            coach_message,
            window,
            thread_id,
            checkpointer=checkpointer,
            message_id=message_id,
            annotation_trace_recorder=record_annotation_trace,
        )
