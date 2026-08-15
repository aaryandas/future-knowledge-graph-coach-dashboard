import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type {
  ChartAxes,
  ChartKind,
  DashboardMessage,
  DataChartPart,
} from "@/lib/parts";
import { CopilotChart } from "./copilot-chart";
import { CopilotMessage } from "./copilot-sidebar";

const percentAxes: ChartAxes = {
  x: {
    label: "Week of",
    values: ["2026-05-26", "2026-06-02"],
  },
  y: {
    label: "Completion",
    unit: "percent",
    minimum: 0,
    maximum: 100,
    ticks: [0, 25, 50, 75, 100],
  },
};

const charts: Record<ChartKind, DataChartPart> = {
  adherence_trend: {
    type: "data-chart",
    data: {
      kind: "adherence_trend",
      window: "28-days",
      axes: percentAxes,
      series: [
        {
          observed_at: "2026-05-26",
          completion_percent: 75,
          observation_node_id: "observation:adherence:2026-05-26",
        },
        {
          observed_at: "2026-06-02",
          completion_percent: 50,
          observation_node_id: "observation:adherence:2026-06-02",
        },
      ],
      observation_node_ids: [
        "observation:adherence:2026-05-26",
        "observation:adherence:2026-06-02",
      ],
    },
  },
  sleep_week: {
    type: "data-chart",
    data: {
      kind: "sleep_week",
      window: "7-days",
      axes: {
        x: {
          label: "Night",
          values: ["2026-06-02", "2026-06-03"],
        },
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
        {
          observed_at: "2026-06-03",
          hours: 6.3,
          observation_node_id: "observation:sleep:2026-06-03",
        },
      ],
      observation_node_ids: [
        "observation:sleep:2026-06-02",
        "observation:sleep:2026-06-03",
      ],
    },
  },
  message_pattern: {
    type: "data-chart",
    data: {
      kind: "message_pattern",
      window: "7-days",
      axes: {
        x: {
          label: "Date",
          values: ["2026-06-02", "2026-06-03"],
        },
        y: {
          label: "Messages",
          unit: "count",
          minimum: 0,
          maximum: 3,
          ticks: [0, 1, 2, 3],
        },
      },
      series: [
        {
          date: "2026-06-02",
          member_count: 2,
          coach_count: 1,
          observation_node_id: "observation:messages:2026-06-02",
        },
        {
          date: "2026-06-03",
          member_count: 1,
          coach_count: 1,
          observation_node_id: "observation:messages:2026-06-03",
        },
      ],
      observation_node_ids: [
        "observation:messages:2026-06-02",
        "observation:messages:2026-06-03",
      ],
    },
  },
  four_week_comparison: {
    type: "data-chart",
    data: {
      kind: "four_week_comparison",
      window: "28-days",
      axes: percentAxes,
      series: [
        {
          week_of: "2026-05-26",
          completion_percent: 75,
          observation_node_id: "observation:adherence:2026-05-26",
        },
        {
          week_of: "2026-06-02",
          completion_percent: 50,
          observation_node_id: "observation:adherence:2026-06-02",
        },
      ],
      observation_node_ids: [
        "observation:adherence:2026-05-26",
        "observation:adherence:2026-06-02",
      ],
    },
  },
};

afterEach(cleanup);

describe("CopilotChart", () => {
  it.each(Object.entries(charts))(
    "renders server-built %s series on the exact typed axes",
    async (kind, part) => {
      const { container } = render(<CopilotChart part={part} />);
      const figure = container.querySelector(
        `[data-chart-kind="${kind}"]`,
      );

      expect(figure).not.toBeNull();
      expect(figure?.textContent).toContain(part.data.axes.y.label);
      for (const tick of part.data.axes.y.ticks) {
        expect(figure?.textContent).toContain(String(tick));
      }
      const geometrySelector =
        kind === "adherence_trend" ? ".recharts-line" : ".recharts-bar";
      await waitFor(() => {
        expect(figure?.querySelector("svg")).not.toBeNull();
        expect(figure?.querySelector(geometrySelector)).not.toBeNull();
      });
    },
  );

  it("shows the empty chart state without inventing values", () => {
    const emptyPart: DataChartPart = {
      type: "data-chart",
      data: {
        kind: "adherence_trend",
        window: "28-days",
        axes: {
          ...percentAxes,
          x: { ...percentAxes.x, values: [] },
        },
        series: [],
        observation_node_ids: [],
      },
    };

    const { container } = render(<CopilotChart part={emptyPart} />);

    expect(screen.getByText("No chart data for this window.")).toBeDefined();
    expect(container.querySelector("svg")).toBeNull();
  });

  it("keeps chart values isolated from model prose", () => {
    const message: DashboardMessage = {
      id: "assistant-structured-values",
      role: "assistant",
      parts: [
        { type: "text", text: "The prose guesses 999 percent." },
        charts.adherence_trend,
      ],
    };

    const { container } = render(<CopilotMessage message={message} />);
    const figure = container.querySelector("figure");

    expect(screen.getByText("The prose guesses 999 percent.")).toBeDefined();
    expect(figure?.textContent).toContain("50% completion");
    expect(figure?.textContent).not.toContain("999");
  });

  it("re-renders a replayed typed data-chart part", () => {
    const replayedMessage: DashboardMessage = {
      id: "assistant-replayed-chart",
      role: "assistant",
      parts: [
        charts.sleep_week,
        { type: "text", text: "Sleep chart restored." },
      ],
    };

    const { container } = render(<CopilotMessage message={replayedMessage} />);
    const figure = container.querySelector('[data-chart-kind="sleep_week"]');

    expect(screen.getByText("Sleep chart restored.")).toBeDefined();
    expect(figure?.getAttribute("data-observation-node-ids")).toBe(
      charts.sleep_week.data.observation_node_ids.join(" "),
    );
    expect(figure?.textContent).toContain("6.3 hours");
  });
});
