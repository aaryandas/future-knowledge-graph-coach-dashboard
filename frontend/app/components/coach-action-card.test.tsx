import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  DashboardMessage,
  DataActionPart,
  SessionPlanActionRow,
} from "@/lib/parts";
import { CoachActionCard } from "./coach-action-card";
import { CopilotMessage } from "./copilot-sidebar";

afterEach(cleanup);

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
        actor: null,
        timestamp: null,
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
        actor: null,
        timestamp: null,
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
        actor: null,
        timestamp: null,
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

  it("edits the member message without resolving it, then confirms the edited payload once", async () => {
    const resolveAction = vi.fn(async () => {});
    render(
      <CoachActionCard
        part={messagePart()}
        onResolve={resolveAction}
      />,
    );

    expect(resolveAction).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Edit send member message" }),
    );
    fireEvent.change(screen.getByLabelText("Message to send"), {
      target: { value: "Edited by the coach" },
    });
    expect(resolveAction).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", { name: "Confirm send member message" }),
    );

    await waitFor(() => expect(resolveAction).toHaveBeenCalledTimes(1));
    expect(resolveAction).toHaveBeenCalledWith({
      decision: "confirm",
      action: {
        kind: "send-member-message",
        message: "Edited by the coach",
        coach_task_id: "task-celebrate",
      },
    });
  });

  it("edits the CoachTask without resolving it, then confirms the edited payload once", async () => {
    const resolveAction = vi.fn(async () => {});
    render(
      <CoachActionCard
        part={taskPart()}
        currentCoachTask={{
          id: "task-celebrate",
          status: "open",
          text: "Celebrate the completed session",
        }}
        onResolve={resolveAction}
      />,
    );

    expect(resolveAction).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Edit update brief task" }),
    );
    fireEvent.change(screen.getByLabelText("Task text"), {
      target: { value: "Celebrate the edited session" },
    });
    fireEvent.change(screen.getByLabelText("Task status"), {
      target: { value: "dismissed" },
    });
    expect(resolveAction).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", { name: "Confirm update brief task" }),
    );

    await waitFor(() => expect(resolveAction).toHaveBeenCalledTimes(1));
    expect(resolveAction).toHaveBeenCalledWith({
      decision: "confirm",
      action: {
        kind: "update-brief-task",
        coach_task_id: "task-celebrate",
        status: "dismissed",
        text: "Celebrate the edited session",
      },
    });
  });

  it("routes session-plan editing to the session table without resolving the proposal", () => {
    const resolveAction = vi.fn(async () => {});
    render(
      <CoachActionCard
        part={sessionPlanPart()}
        onResolve={resolveAction}
      />,
    );

    expect(resolveAction).not.toHaveBeenCalled();
    expect(
      screen.getByText(
        "Edit the session table to compose a new proposal for review.",
      ),
    ).toBeDefined();
    const editLink = screen.getByRole("link", {
      name: "Edit in session table",
    });
    expect(editLink.getAttribute("href")).toBe("#session-title");
    expect(
      screen.queryByRole("button", { name: "Edit update session plan" }),
    ).toBeNull();
    fireEvent.click(editLink);
    expect(resolveAction).not.toHaveBeenCalled();
  });

  it.each([
    ["send-member-message", messagePart()],
    ["update-brief-task", taskPart()],
    ["write-session-plan", sessionPlanPart()],
  ])("discards one pending %s only after the control is clicked", async (_kind, part) => {
    const resolveAction = vi.fn(async () => {});
    render(<CoachActionCard part={part} onResolve={resolveAction} />);

    expect(resolveAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /^Discard / }));

    await waitFor(() => expect(resolveAction).toHaveBeenCalledTimes(1));
    expect(resolveAction).toHaveBeenCalledWith({ decision: "discard" });
  });

  it.each([
    ["send-member-message", messagePart()],
    ["update-brief-task", taskPart()],
    ["write-session-plan", sessionPlanPart()],
  ])("confirms one pending %s exactly once", async (_kind, part) => {
    const resolveAction = vi.fn(async () => {});
    render(<CoachActionCard part={part} onResolve={resolveAction} />);

    expect(resolveAction).not.toHaveBeenCalled();
    const confirm = screen.getByRole("button", { name: /^Confirm / });
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    await waitFor(() => expect(resolveAction).toHaveBeenCalledTimes(1));
  });

  it("shows the execution actor and timestamp returned by a confirmed action", () => {
    const part = messagePart();
    part.data.status = "confirmed";
    part.data.actor = "coach-1";
    part.data.timestamp = "2026-06-04T09:00:00+00:00";

    render(<CoachActionCard part={part} />);

    expect(screen.getByText("coach-1")).toBeDefined();
    expect(screen.getByText("2026-06-04T09:00:00+00:00")).toBeDefined();
  });

  it("routes a card resolution through its copilot message and action ids", async () => {
    const onResolveAction = vi.fn(async () => {});
    const message: DashboardMessage = {
      id: "assistant-action-1",
      role: "assistant",
      parts: [messagePart()],
    };
    render(
      <CopilotMessage
        message={message}
        onResolveAction={onResolveAction}
      />,
    );

    expect(onResolveAction).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Discard send member message" }),
    );

    await waitFor(() => expect(onResolveAction).toHaveBeenCalledTimes(1));
    expect(onResolveAction).toHaveBeenCalledWith(
      "assistant-action-1",
      "send-message-1",
      { decision: "discard" },
    );
  });
});

function messagePart(): DataActionPart {
  return {
    type: "data-action",
    data: {
      action_id: "send-message-1",
      status: "pending",
      action: {
        kind: "send-member-message",
        message: "Original draft",
        coach_task_id: "task-celebrate",
      },
      actor: null,
      timestamp: null,
    },
  };
}

function taskPart(): DataActionPart {
  return {
    type: "data-action",
    data: {
      action_id: "update-task-1",
      status: "pending",
      action: {
        kind: "update-brief-task",
        coach_task_id: "task-celebrate",
        status: "completed",
        text: "Celebrate the completed session",
      },
      actor: null,
      timestamp: null,
    },
  };
}

function sessionPlanPart(): DataActionPart {
  const row = sessionPlanRow("row-1", "exercise-squat", 3, 8);
  return {
    type: "data-action",
    data: {
      action_id: "write-plan-1",
      status: "pending",
      action: {
        kind: "write-session-plan",
        session_id: "session-2026-08-15",
        edits: [{ kind: "edit", row: { ...row, reps: 10 } }],
        old_rows: [row],
        new_rows: [{ ...row, reps: 10 }],
        verdicts: [],
        failure: null,
      },
      actor: null,
      timestamp: null,
    },
  };
}

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
