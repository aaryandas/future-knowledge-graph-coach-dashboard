"use client";

import { useId } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DataChart, DataChartPart, NumericAxis } from "@/lib/parts";

const chartTitles = {
  adherence_trend: "Adherence trend",
  sleep_week: "Sleep week",
  message_pattern: "Message pattern",
  four_week_comparison: "Four-week comparison",
} as const;

export function CopilotChart({ part }: { part: DataChartPart }) {
  const chart = part.data;
  const title = chartTitles[chart.kind];
  const titleId = useId();

  if (chart.series.length === 0) {
    return (
      <section
        className="copilot-chart-empty"
        aria-label={title}
        data-chart-kind={chart.kind}
      >
        <strong>{title}</strong>
        <span>No chart data for this window.</span>
      </section>
    );
  }

  return (
    <figure
      className="copilot-chart"
      aria-labelledby={titleId}
      data-chart-kind={chart.kind}
      data-observation-node-ids={chart.observation_node_ids.join(" ")}
    >
      <figcaption id={titleId}>
        <span>{title}</span>
        <span>{formatWindow(chart.window)}</span>
      </figcaption>
      <div className="copilot-chart-scale">
        <span>{formatAxisName(chart.axes.y)}</span>
        <ol aria-label={`${chart.axes.y.label} axis values`}>
          {chart.axes.y.ticks.map((tick) => (
            <li key={tick}>{formatAxisValue(tick, chart.axes.y.unit)}</li>
          ))}
        </ol>
      </div>
      <div className="copilot-chart-canvas">{renderChart(chart)}</div>
      <div className="copilot-chart-domain">
        <span>{chart.axes.x.label}</span>
        <span>{formatDomain(chart.axes.x.values)}</span>
      </div>
      <ul className="sr-only" aria-label={`${title} data`}>
        {describeSeries(chart).map((description, index) => (
          <li key={chart.observation_node_ids[index]}>{description}</li>
        ))}
      </ul>
    </figure>
  );
}

function renderChart(chart: DataChart) {
  const axisProps = {
    domain: [chart.axes.y.minimum, chart.axes.y.maximum] as [number, number],
    ticks: chart.axes.y.ticks,
    tickFormatter: (value: number) =>
      formatAxisValue(value, chart.axes.y.unit),
  };
  const xAxis = (
    <XAxis
      dataKey={xAxisDataKey(chart)}
      tickLine={false}
      axisLine={{ stroke: "var(--chart-axis)" }}
      tick={{ fill: "var(--foreground-muted)", fontSize: 10 }}
      tickMargin={8}
      minTickGap={12}
      tickFormatter={formatDate}
    />
  );
  const yAxis = (
    <YAxis
      {...axisProps}
      width={34}
      allowDataOverflow
      tickLine={false}
      axisLine={false}
      tick={{ fill: "var(--foreground-muted)", fontSize: 10 }}
    />
  );
  const tooltip = (
    <Tooltip
      cursor={{ fill: "var(--surface-hover)" }}
      contentStyle={{
        background: "var(--surface)",
        border: "1px solid var(--border-strong)",
        borderRadius: "7px",
        color: "var(--foreground)",
        fontSize: "11px",
      }}
      labelFormatter={(label) => formatDate(String(label))}
      formatter={(value) =>
        formatAxisValue(Number(value), chart.axes.y.unit)
      }
    />
  );

  switch (chart.kind) {
    case "adherence_trend":
      return (
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <LineChart
            data={chart.series}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
            accessibilityLayer
          >
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            {xAxis}
            {yAxis}
            {tooltip}
            <Line
              type="linear"
              dataKey="completion_percent"
              name="Completion"
              stroke="var(--accent)"
              strokeWidth={2}
              dot={{ r: 3, fill: "var(--surface)", strokeWidth: 2 }}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      );
    case "sleep_week":
      return (
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <BarChart
            data={chart.series}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
            accessibilityLayer
          >
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            {xAxis}
            {yAxis}
            {tooltip}
            <Bar
              dataKey="hours"
              name="Sleep"
              fill="var(--data-blue)"
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      );
    case "message_pattern":
      return (
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <BarChart
            data={chart.series}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
            accessibilityLayer
          >
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            {xAxis}
            {yAxis}
            {tooltip}
            <Legend
              iconType="circle"
              iconSize={7}
              wrapperStyle={{ fontSize: 10 }}
              formatter={(value) => (
                <span className="copilot-chart-legend-label">{value}</span>
              )}
            />
            <Bar
              dataKey="member_count"
              name="Member"
              stackId="messages"
              fill="var(--accent)"
              isAnimationActive={false}
            />
            <Bar
              dataKey="coach_count"
              name="Coach"
              stackId="messages"
              fill="var(--data-orange)"
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      );
    case "four_week_comparison":
      return (
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <BarChart
            data={chart.series}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
            accessibilityLayer
          >
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            {xAxis}
            {yAxis}
            {tooltip}
            <Bar
              dataKey="completion_percent"
              name="Completion"
              fill="var(--accent)"
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      );
  }
}

function xAxisDataKey(chart: DataChart): string {
  switch (chart.kind) {
    case "adherence_trend":
    case "sleep_week":
      return "observed_at";
    case "message_pattern":
      return "date";
    case "four_week_comparison":
      return "week_of";
  }
}

function formatAxisName(axis: NumericAxis): string {
  if (axis.unit === "count") {
    return axis.label;
  }
  return `${axis.label} · ${axis.unit}`;
}

function formatAxisValue(value: number, unit: string): string {
  if (unit === "percent") {
    return `${value}%`;
  }
  if (unit === "hours") {
    return `${value}h`;
  }
  return String(value);
}

function formatWindow(window: DataChart["window"]): string {
  return window.replace("-", " ");
}

function formatDomain(values: string[]): string {
  const first = values[0];
  const last = values.at(-1);
  if (first === undefined || last === undefined) {
    return "No dates";
  }
  if (first === last) {
    return formatDate(first);
  }
  return `${formatDate(first)} – ${formatDate(last)}`;
}

function formatDate(value: string): string {
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function describeSeries(chart: DataChart): string[] {
  switch (chart.kind) {
    case "adherence_trend":
      return chart.series.map(
        (point) =>
          `${point.observed_at}: ${point.completion_percent}% completion. Observation ${point.observation_node_id}.`,
      );
    case "sleep_week":
      return chart.series.map(
        (point) =>
          `${point.observed_at}: ${point.hours} hours. Observation ${point.observation_node_id}.`,
      );
    case "message_pattern":
      return chart.series.map(
        (point) =>
          `${point.date}: ${point.member_count} member messages and ${point.coach_count} coach messages. Observation ${point.observation_node_id}.`,
      );
    case "four_week_comparison":
      return chart.series.map(
        (point) =>
          `${point.week_of}: ${point.completion_percent}% completion. Observation ${point.observation_node_id}.`,
      );
  }
}
