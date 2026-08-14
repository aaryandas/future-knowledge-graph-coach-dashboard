from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import psycopg
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from neo4j.exceptions import DriverError, Neo4jError
from pydantic import BaseModel, ConfigDict

from app.api.copilot import copilot_turn_stream
from app.api.copilot_action_models import CoachAction
from app.copilot import CopilotConflict, CopilotTurnResult, resume_copilot_action


class CoachActionResolution(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: Literal["confirm", "discard"]
    action: CoachAction | None = None


type ActionResumer = Callable[[str, str, dict[str, object]], CopilotTurnResult]


def create_copilot_actions_router(
    action_resumer: ActionResumer = resume_copilot_action,
) -> APIRouter:
    router = APIRouter(prefix="/api/members/{member_id}/copilot/actions")

    @router.post("/{action_id}/confirm")
    def confirm_action(
        member_id: str,
        action_id: str,
        request: CoachActionResolution,
    ) -> StreamingResponse:
        resolution: dict[str, object] = {"decision": request.decision}
        if request.action is not None:
            resolution["action"] = request.action.model_dump(mode="json")
        try:
            result = action_resumer(member_id, action_id, resolution)
        except psycopg.Error as error:
            raise HTTPException(
                status_code=503,
                detail="Copilot thread storage is unavailable.",
            ) from error
        except (DriverError, Neo4jError) as error:
            raise HTTPException(
                status_code=503,
                detail="Member Context Graph (KG2) is unavailable.",
            ) from error
        if isinstance(result, CopilotConflict):
            raise HTTPException(status_code=409, detail=result.detail)
        return StreamingResponse(
            copilot_turn_stream(result),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "x-vercel-ai-ui-message-stream": "v1",
            },
        )

    return router


router = create_copilot_actions_router()
