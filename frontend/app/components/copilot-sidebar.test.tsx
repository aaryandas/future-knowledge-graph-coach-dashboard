import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DashboardMessage } from "@/lib/parts";
import { CopilotMessage, CopilotSidebar } from "./copilot-sidebar";

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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

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

  it.each([
    ["Show me the brief"],
    ["How's adherence trending?"],
    ["Sleep this week"],
    ["What changed since last week?"],
  ])("submits the canonical quick prompt as a Copilot turn: %s", async (message) => {
    vi.stubGlobal("fetch", pendingFetch());
    renderSidebar([]);

    fireEvent.click(
      screen.getByRole("button", { name: `Ask Copilot: ${message}` }),
    );

    await waitFor(() => {
      expect(
        within(screen.getByRole("log", { name: "Copilot conversation" }))
          .getByText(message),
      ).toBeDefined();
    });
  });

  it("renders churn Barriers with exact evidence and auditable Source chips", () => {
    const message: DashboardMessage = {
      id: "assistant-churn-risk",
      role: "assistant",
      parts: [
        { type: "text", text: "Jordan's churn risk is elevated." },
        {
          type: "data-brief",
          data: {
            generated_for: "2026-06-04",
            churn_risk_level: "elevated",
            churn_risk_reasons: ["Adherence declined."],
            barriers: [
              {
                node_id: "barrier:adherence-decline",
                kind: "adherence-decline",
                copper_id: "copper:barrier:adherence-decline",
                reason: "Completion fell across the latest four weeks.",
                risk_level: "high",
                evidence_node_ids: [
                  "observation:adherence:2026-05-26",
                  "workout-session:2026-06-02",
                ],
              },
            ],
            coach_tasks: [],
          },
        },
        {
          type: "data-sources",
          data: {
            sources: [
              {
                tool: "get_morning_brief",
                node_ids: [
                  "barrier:adherence-decline",
                  "observation:adherence:2026-05-26",
                ],
              },
            ],
          },
        },
      ],
    };

    const { container } = render(<CopilotMessage message={message} />);

    expect(screen.getByRole("region", { name: "Barriers" })).toBeDefined();
    expect(screen.getByText("Adherence decline")).toBeDefined();
    const evidence = screen.getByRole("list", {
      name: "Evidence for Adherence decline",
    });
    expect(
      within(evidence).getByText("observation:adherence:2026-05-26"),
    ).toBeDefined();
    expect(
      within(evidence).getByText("workout-session:2026-06-02"),
    ).toBeDefined();
    const source = container.querySelector(
      '[data-source-tool="get_morning_brief"]',
    );
    expect(source).not.toBeNull();
    fireEvent.click(
      within(source as HTMLElement).getByLabelText(
        "morning brief source: show 2 graph node IDs",
      ),
    );
    expect(
      within(source as HTMLElement).getByText("barrier:adherence-decline"),
    ).toBeDefined();
    expect(
      within(source as HTMLElement).getByText(
        "observation:adherence:2026-05-26",
      ),
    ).toBeDefined();
  });

  it("shows when an answer has no graph sources", () => {
    const message: DashboardMessage = {
      id: "assistant-no-sources",
      role: "assistant",
      parts: [
        { type: "text", text: "I could not answer that question." },
        { type: "data-sources", data: { sources: [] } },
      ],
    };

    render(<CopilotMessage message={message} />);

    expect(screen.getByText("No graph sources")).toBeDefined();
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

function pendingFetch(): typeof fetch {
  return vi.fn(
    (_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      }),
  );
}
