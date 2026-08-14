export type GraphNodeKind =
  | "Exercise"
  | "MuscleGroup"
  | "Joint"
  | "MovementPattern"
  | "Equipment"
  | "Injury"
  | "AnatomicalStructure"
  | "ClinicalFinding"
  | "Member"
  | "Goal"
  | "MemberInjury"
  | "WorkoutSession"
  | "Observation"
  | "ChatMessage"
  | "Barrier"
  | "CoachTask";

export type GraphEdgeKind =
  | "targets"
  | "loads"
  | "performs"
  | "requires"
  | "findingSite"
  | "isA"
  | "exactMatch"
  | "contraindicates"
  | "pursues"
  | "has"
  | "owns"
  | "performed"
  | "observed"
  | "said"
  | "received"
  | "dislikes"
  | "included"
  | "evidencedBy"
  | "addresses";

export type GraphName =
  | "Movement/Clinical Graph (KG1)"
  | "Member Context Graph (KG2)";

export type GraphPropertyValue =
  | string
  | number
  | boolean
  | null
  | string[]
  | number[]
  | boolean[];

export interface GraphNode {
  id: string;
  kind: GraphNodeKind;
  graph: GraphName;
  label: string;
  properties: Record<string, GraphPropertyValue>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: GraphEdgeKind;
}

export interface GraphNeighborhoodPart {
  type: "data-graph-neighborhood";
  member_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}
