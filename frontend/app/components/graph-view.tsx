"use client";

import { useMemo, useState, type CSSProperties } from "react";
import { useCopilotSidebar } from "./copilot-sidebar-context";
import type {
  GraphNeighborhoodPart,
  GraphNode,
  GraphNodeKind,
  GraphPropertyValue,
} from "@/lib/parts";

const viewBox = { width: 1120, height: 500 } as const;
const nodeHeight = 42;

interface PositionedNode extends GraphNode {
  x: number;
  y: number;
  width: number;
}

interface NodeLane {
  x: number;
  firstY: number;
  gap: number;
  width: number;
}

const nodeLanes: Partial<Record<GraphNodeKind, NodeLane>> = {
  Member: { x: 34, firstY: 228, gap: 0, width: 132 },
  Goal: { x: 194, firstY: 70, gap: 58, width: 172 },
  MemberInjury: { x: 194, firstY: 228, gap: 0, width: 172 },
  Equipment: { x: 194, firstY: 346, gap: 54, width: 172 },
  ClinicalFinding: { x: 396, firstY: 228, gap: 0, width: 150 },
  Injury: { x: 576, firstY: 228, gap: 0, width: 150 },
  MovementPattern: { x: 756, firstY: 228, gap: 0, width: 164 },
  Exercise: { x: 948, firstY: 72, gap: 62, width: 160 },
};

const fallbackLane: NodeLane = { x: 470, firstY: 360, gap: 50, width: 170 };
const previewPropertyLabels: Record<string, string> = {
  age: "age",
  bilateral_pair_id: "bilateral pairing",
  code: "SNOMED code",
  height_cm: "height (cm)",
  is_bilateral: "bilateral pairing",
  joint: "Joint",
  member_since: "member since",
  name: "name",
  notes: "notes",
  preferred_term: "preferred term",
  priority: "priority",
  priority_tier: "priority tier",
  region: "region",
  severity: "severity",
  side: "side",
  since: "since",
  snomedct_hint: "SNOMED hint",
  status: "status",
  synonyms: "synonyms",
  target_date: "target date",
  text: "goal",
  tier: "tier",
  timezone: "timezone",
  weight_kg: "weight (kg)",
};

export function GraphView({ part }: { part: GraphNeighborhoodPart | null }) {
  if (part === null) {
    return (
      <div className="graph-state glass" role="status">
        Graph neighborhood is unavailable.
      </div>
    );
  }
  return <GraphCanvas part={part} />;
}

function GraphCanvas({ part }: { part: GraphNeighborhoodPart }) {
  const { prefillMessage } = useCopilotSidebar();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const nodes = useMemo(() => positionNodes(part.nodes), [part.nodes]);
  const nodeById = useMemo(
    () => new Map(nodes.map((node) => [node.id, node])),
    [nodes],
  );
  const selectedNode =
    selectedId === null ? null : (nodeById.get(selectedId) ?? null);
  const edgeKinds = new Set<string>();

  function askCopilot(node: GraphNode) {
    prefillMessage(
      `How does ${node.kind} “${node.label}” affect Jordan Rivera's plan?`,
    );
  }

  return (
    <section className="graph-card glass" aria-label="Graph neighborhood">
      <div className="graph-canvas">
        <svg
          className="graph-svg"
          viewBox={`0 0 ${viewBox.width} ${viewBox.height}`}
          role="img"
          aria-label="Jordan Rivera graph neighborhood"
        >
          <defs>
            <marker
              id="graph-arrow"
              viewBox="0 0 8 8"
              refX="7"
              refY="4"
              markerWidth="7"
              markerHeight="7"
              orient="auto"
            >
              <path d="M0 0 8 4 0 8Z" fill="var(--foreground-subtle)" />
            </marker>
            <filter id="graph-pencil" x="-5%" y="-10%" width="110%" height="120%">
              <feTurbulence
                type="fractalNoise"
                baseFrequency="0.035"
                numOctaves="2"
                seed="29"
                result="noise"
              />
              <feDisplacementMap
                in="SourceGraphic"
                in2="noise"
                scale="1.15"
              />
            </filter>
          </defs>

          <g className="graph-rules" aria-hidden="true">
            {[66, 128, 190, 252, 314, 376, 438].map((y, index) => (
              <path
                key={y}
                d={`M24 ${y} C 300 ${y + (index % 2 === 0 ? 1 : -1)}, 820 ${y - 1}, 1096 ${y}`}
              />
            ))}
          </g>

          <g className="graph-edges" aria-hidden="true">
            {part.edges.map((edge, index) => {
              const source = nodeById.get(edge.source);
              const target = nodeById.get(edge.target);
              if (source === undefined || target === undefined) {
                return null;
              }
              const path = edgePath(source, target, index);
              const showTag = !edgeKinds.has(edge.kind);
              edgeKinds.add(edge.kind);
              const tag = edgeTagPosition(source, target);
              return (
                <g key={edge.id} data-edge-kind={edge.kind}>
                  <path className="graph-edge-underlay" d={path} />
                  <path
                    className="graph-edge"
                    d={path}
                    markerEnd="url(#graph-arrow)"
                  />
                  {showTag ? (
                    <g className="graph-edge-tag" transform={`translate(${tag.x} ${tag.y})`}>
                      <rect x="-44" y="-9" width="88" height="18" rx="9" />
                      <text textAnchor="middle" dominantBaseline="central">
                        {edge.kind}
                      </text>
                    </g>
                  ) : null}
                </g>
              );
            })}
          </g>

          <g className="graph-nodes">
            {nodes.map((node) => (
              <foreignObject
                key={node.id}
                x={node.x}
                y={node.y}
                width={node.width}
                height={nodeHeight}
                overflow="visible"
              >
                <button
                  type="button"
                  className="graph-node press"
                  data-graph={node.graph}
                  aria-label={`${node.kind}: ${node.label}`}
                  aria-pressed={selectedId === node.id}
                  onClick={() => setSelectedId(node.id)}
                >
                  <span className="graph-node-value">{node.label}</span>
                  <span className="graph-node-kind">{node.kind}</span>
                </button>
              </foreignObject>
            ))}
          </g>
        </svg>

        {selectedNode === null ? null : (
          <NodePreview
            node={selectedNode}
            onAskCopilot={() => askCopilot(selectedNode)}
            onClose={() => setSelectedId(null)}
          />
        )}
      </div>

      <div className="graph-legend" aria-label="Graph key">
        <span>
          <i data-graph="Member Context Graph (KG2)" />
          Member Context Graph (KG2)
        </span>
        <span>
          <i data-graph="Movement/Clinical Graph (KG1)" />
          Movement/Clinical Graph (KG1)
        </span>
      </div>
    </section>
  );
}

function NodePreview({
  node,
  onAskCopilot,
  onClose,
}: {
  node: PositionedNode;
  onAskCopilot(): void;
  onClose(): void;
}) {
  const properties = previewProperties(node);
  const previewStyle = {
    "--preview-x": `${Math.min(node.x + node.width + 12, 842) / viewBox.width * 100}%`,
    "--preview-y": `${Math.min(node.y + nodeHeight + 10, 300) / viewBox.height * 100}%`,
  } as CSSProperties;

  return (
    <aside
      className="graph-preview glass"
      style={previewStyle}
      aria-label={`${node.kind} preview`}
    >
      <div className="graph-preview-heading">
        <span>{node.kind}</span>
        <button type="button" onClick={onClose} aria-label="Close node preview">
          ×
        </button>
      </div>
      <strong>{node.label}</strong>
      <dl>
        {properties.map(({ key, label, value }) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{formatProperty(value)}</dd>
          </div>
        ))}
      </dl>
      <button type="button" className="graph-preview-ask press" onClick={onAskCopilot}>
        Ask copilot <span aria-hidden="true">→</span>
      </button>
    </aside>
  );
}

export function GraphSkeleton() {
  return (
    <div className="graph-card glass skeleton-shimmer" aria-label="Loading graph neighborhood">
      <svg
        className="graph-svg"
        viewBox={`0 0 ${viewBox.width} ${viewBox.height}`}
        aria-hidden="true"
      >
        {[90, 220, 350].map((y) => (
          <path key={y} className="graph-skeleton-line" d={`M100 ${y} C 360 ${y - 30} 760 ${y + 30} 1020 ${y}`} />
        ))}
        {[120, 310, 520, 730, 940].map((x, index) => (
          <rect
            key={x}
            className="graph-skeleton-node"
            x={x}
            y={95 + (index % 3) * 125}
            width="150"
            height={nodeHeight}
            rx={nodeHeight / 2}
          />
        ))}
      </svg>
    </div>
  );
}

function previewProperties(node: GraphNode) {
  const properties = Object.entries(node.properties).flatMap(([key, value]) => {
    const label = previewPropertyLabels[key];
    return label === undefined ? [] : [{ key, label, value }];
  });
  if (properties.length === 0) {
    return [{ key: "name", label: "name", value: node.label }];
  }
  return properties.slice(0, 4);
}

function positionNodes(nodes: GraphNode[]): PositionedNode[] {
  const counts = new Map<GraphNodeKind, number>();
  return nodes.map((node) => {
    const lane = nodeLanes[node.kind] ?? fallbackLane;
    const index = counts.get(node.kind) ?? 0;
    counts.set(node.kind, index + 1);
    return {
      ...node,
      x: lane.x,
      y: lane.firstY + lane.gap * index,
      width: lane.width,
    };
  });
}

function edgePath(
  source: PositionedNode,
  target: PositionedNode,
  index: number,
): string {
  const sourceCenterX = source.x + source.width / 2;
  const targetCenterX = target.x + target.width / 2;
  const movesRight = sourceCenterX <= targetCenterX;
  const sourceX = movesRight ? source.x + source.width : source.x;
  const targetX = movesRight ? target.x : target.x + target.width;
  const sourceY = source.y + nodeHeight / 2;
  const targetY = target.y + nodeHeight / 2;
  const midpoint = (sourceX + targetX) / 2 + ((index % 3) - 1) * 2;
  return `M ${sourceX} ${sourceY} C ${midpoint} ${sourceY}, ${midpoint} ${targetY}, ${targetX} ${targetY}`;
}

function edgeTagPosition(
  source: PositionedNode,
  target: PositionedNode,
): { x: number; y: number } {
  return {
    x: (source.x + source.width / 2 + target.x + target.width / 2) / 2,
    y: (source.y + target.y) / 2 + nodeHeight / 2 - 13,
  };
}

function formatProperty(value: GraphPropertyValue): string {
  if (Array.isArray(value)) {
    return value.join(" · ");
  }
  if (value === null) {
    return "null";
  }
  return String(value);
}
