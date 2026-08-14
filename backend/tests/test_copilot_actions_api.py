import json

from app.api.copilot_action_models import DataActionPart
from app.api.copilot_actions import ActionResumer, create_copilot_actions_router
from app.api.copilot_brief_models import DataBriefPart
from app.copilot import CopilotDataPart, CopilotTurn
from fastapi import FastAPI
from fastapi.testclient import TestClient

MEMBER_ID = "mbr_01HX9JORDAN"


def test_confirm_route_resumes_the_member_thread_with_the_edited_action() -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    def resume_action(
        member_id: str,
        action_id: str,
        resolution: dict[str, object],
    ) -> CopilotTurn:
        calls.append((member_id, action_id, resolution))
        return CopilotTurn(
            message_id="action-send-1",
            text="Message sent.",
            data_parts=(
                CopilotDataPart(type="data-sources", data={"sources": []}),
                _action_part("confirmed", message="Edited by the coach"),
            ),
        )

    response = _client(resume_action).post(
        f"/api/members/{MEMBER_ID}/copilot/actions/send-1/confirm",
        json={
            "decision": "confirm",
            "action": {
                "kind": "send-member-message",
                "message": "Edited by the coach",
                "coach_task_id": "task-1",
            },
        },
    )

    assert response.status_code == 200
    assert calls == [
        (
            MEMBER_ID,
            "send-1",
            {
                "decision": "confirm",
                "action": {
                    "kind": "send-member-message",
                    "message": "Edited by the coach",
                    "coach_task_id": "task-1",
                },
            },
        )
    ]
    assert [event["type"] for event in _events(response.text)] == [
        "start",
        "start-step",
        "data-sources",
        "data-action",
        "text-start",
        "text-delta",
        "text-end",
        "finish-step",
        "finish",
    ]


def test_confirm_route_maps_a_non_pending_action_to_conflict() -> None:
    def reject_action(
        member_id: str,
        action_id: str,
        resolution: dict[str, object],
    ) -> CopilotTurn:
        raise ValueError("The member thread has no pending coach action.")

    response = _client(reject_action).post(
        f"/api/members/{MEMBER_ID}/copilot/actions/missing/confirm",
        json={"decision": "discard"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "The member thread has no pending coach action."
    }


def test_data_action_part_is_a_frozen_discriminated_contract() -> None:
    assert DataActionPart.model_config["frozen"] is True
    schema = DataActionPart.model_json_schema()
    assert schema["properties"]["type"]["const"] == "data-action"
    action_schema = schema["$defs"]["CoachAction"]
    assert action_schema["discriminator"]["propertyName"] == "kind"
    assert set(action_schema["discriminator"]["mapping"]) == {
        "send-member-message",
        "update-brief-task",
    }


def test_data_brief_part_is_a_frozen_typed_contract() -> None:
    assert DataBriefPart.model_config["frozen"] is True
    schema = DataBriefPart.model_json_schema()
    assert schema["properties"]["type"]["const"] == "data-brief"
    coach_tasks = schema["$defs"]["DataBrief"]["properties"]["coach_tasks"]
    assert coach_tasks["items"] == {"$ref": "#/$defs/CoachTask"}


def _client(action_resumer: ActionResumer) -> TestClient:
    test_app = FastAPI()
    test_app.include_router(create_copilot_actions_router(action_resumer))
    return TestClient(test_app)


def _action_part(
    status: str,
    *,
    message: str,
) -> CopilotDataPart:
    return CopilotDataPart(
        type="data-action",
        data={
            "action_id": "send-1",
            "status": status,
            "action": {
                "kind": "send-member-message",
                "message": message,
                "coach_task_id": "task-1",
            },
        },
    )


def _events(stream: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in stream.splitlines()
        if line.startswith("data: {")
    ]
