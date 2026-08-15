import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type {
  DataActionPart,
  SessionPlanActionRow,
} from "@/lib/parts";
import { CoachActionCard } from "./coach-action-card";

describe("CoachActionCard", () => {
  it("renders the full pending member message behind visible controls", () => {
    const message =
      "Jordan, your pain-free session was a real win.\nKeep the next one easy and steady.";
    const part: DataActionPart = {
      type: "data-action",
      data: {
        action_id: "send-message-1",
        status: "pending",
        action: {
          kind: "send-member-message",
          message,
          coach_task_id: "task-celebrate",
        },
      },
    };

    const html = renderToStaticMarkup(<CoachActionCard part={part} />);

    expect(html).toContain("Send member message");
    expect(html).toContain("Jordan, your pain-free session was a real win.");
    expect(html).toContain("Keep the next one easy and steady.");
    expect(html.match(/<button/g)).toHaveLength(3);
    expect(html).toContain(">Edit</button>");
    expect(html).toContain(">Discard</button>");
    expect(html).toContain(">Confirm</button>");
    expect(html).not.toContain("<form");
    expect(html).not.toContain("/actions/");
  });

  it("renders exact before and after values for a pending CoachTask update", () => {
    const part: DataActionPart = {
      type: "data-action",
      data: {
        action_id: "update-task-1",
        status: "pending",
        action: {
          kind: "update-brief-task",
          coach_task_id: "task-celebrate",
          status: "completed",
          text: "Celebrate the pain-free 30-minute session",
        },
      },
    };

    const html = renderToStaticMarkup(
      <CoachActionCard
        part={part}
        currentCoachTask={{
          id: "task-celebrate",
          status: "open",
          text: "Celebrate the completed 30-minute session",
        }}
      />,
    );

    expect(html).toContain("task-celebrate");
    expect(html).toContain("Celebrate the completed 30-minute session");
    expect(html).toContain("Celebrate the pain-free 30-minute session");
    expect(html).toContain(">open</del>");
    expect(html).toContain(">completed</ins>");
  });

  it("renders exact changed fields and positions for a session-plan action", () => {
    const first = sessionPlanRow("row-1", "exercise-squat", 3, 8);
    const second = sessionPlanRow("row-2", "exercise-row", 2, 10);
    const editedFirst = { ...first, reps: 10 };
    const part: DataActionPart = {
      type: "data-action",
      data: {
        action_id: "write-plan-1",
        status: "pending",
        action: {
          kind: "write-session-plan",
          session_id: "session-2026-08-15",
          edits: [
            { kind: "edit", row: editedFirst },
            { kind: "reorder", row_id: second.row_id, position: 0 },
          ],
          old_rows: [first, second],
          new_rows: [second, editedFirst],
          verdicts: [],
          failure: null,
        },
      },
    };

    const html = renderToStaticMarkup(<CoachActionCard part={part} />);

    expect(html).toContain("session-2026-08-15");
    expect(html).toContain("row-1");
    expect(html).toContain("row-2");
    expect(html).toContain("Position");
    expect(html).toContain("Reps");
    expect(html).toContain(">8</del>");
    expect(html).toContain(">10</ins>");
  });
});

function sessionPlanRow(
  rowId: string,
  exerciseId: string,
  sets: number,
  reps: number,
): SessionPlanActionRow {
  return {
    row_id: rowId,
    exercise_id: exerciseId,
    section: "main",
    sets,
    reps,
    hold_minutes: null,
    rest_minutes: 1,
    per_side: false,
    supports_weight: true,
    minutes: 4,
  };
}
