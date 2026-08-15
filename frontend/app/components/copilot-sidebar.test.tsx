import { cleanup, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DashboardMessage } from "@/lib/parts";
import { CopilotSidebar } from "./copilot-sidebar";

const persistedMessages: DashboardMessage[] = [
  {
    id: "user-history-1",
    role: "user",
    parts: [{ type: "text", text: "Show Jordan's sleep this week." }],
  },
  {
    id: "assistant-history-1",
    role: "assistant",
    parts: [
      {
        type: "data-chart",
        data: {
          kind: "sleep_week",
          window: "7-days",
          axes: {
            x: { label: "Night", values: ["2026-06-02"] },
            y: {
              label: "Sleep",
              unit: "hours",
              minimum: 0,
              maximum: 9,
              ticks: [0, 3, 6, 9],
            },
          },
          series: [
            {
              observed_at: "2026-06-02",
              hours: 7.8,
              observation_node_id: "observation:sleep:2026-06-02",
            },
          ],
          observation_node_ids: ["observation:sleep:2026-06-02"],
        },
      },
      { type: "text", text: "Jordan averaged 7.8 hours." },
    ],
  },
];

afterEach(cleanup);

describe("CopilotSidebar", () => {
  it("mounts with persisted typed messages and their original ids", () => {
    const { container } = renderSidebar(persistedMessages);

    expect(screen.getByText("Show Jordan's sleep this week.")).toBeDefined();
    expect(screen.getByText("Jordan averaged 7.8 hours.")).toBeDefined();
    expect(
      container.querySelector('[data-message-id="user-history-1"]'),
    ).not.toBeNull();
    expect(
      container.querySelector('[data-message-id="assistant-history-1"]'),
    ).not.toBeNull();
    expect(
      container.querySelector('[data-chart-kind="sleep_week"]'),
    ).not.toBeNull();
    expect(
      screen.queryByText("What can I help with today?"),
    ).toBeNull();
  });

  it("shows the empty state when persisted history has no messages", () => {
    renderSidebar([]);

    expect(screen.getByText("What can I help with today?")).toBeDefined();
  });
});

function renderSidebar(initialMessages: DashboardMessage[]) {
  return render(
    <CopilotSidebar
      memberId="mbr_01HX9JORDAN"
      memberName="Jordan"
      coachTasks={[]}
      composerValue=""
      composerRef={createRef<HTMLInputElement>()}
      hasPlan={false}
      initialMessages={initialMessages}
      onBusyChange={vi.fn()}
      onComposerChange={vi.fn()}
      onConstraints={vi.fn()}
      onPlan={vi.fn()}
      onSubmitterChange={vi.fn()}
      onTrace={vi.fn()}
    />,
  );
}
