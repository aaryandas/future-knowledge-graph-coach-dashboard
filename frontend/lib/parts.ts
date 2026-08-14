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

export type SnapshotTrend = "up" | "down" | "flat" | "neutral";

export interface SnapshotSource {
  observed_at: string;
  age_days: number;
  stale: boolean;
}

export interface MemberSnapshotStat {
  value: string | number | null;
  suffix: string | null;
  trend: SnapshotTrend;
  trend_text: string;
  source: SnapshotSource | null;
}

export interface MemberIdentityGoal {
  id: string;
  text: string;
}

export interface MemberIdentityInjury {
  id: string;
  region: string;
  finding: string | null;
  status: string;
}

export interface MemberIdentity {
  name: string;
  tier: string;
  age: number;
  sex: string;
  member_since: string;
  tenure_days: number;
  injury: MemberIdentityInjury | null;
  goals: MemberIdentityGoal[];
}

export interface MemberSnapshotStats {
  adherence: MemberSnapshotStat;
  sleep: MemberSnapshotStat;
  sessions: MemberSnapshotStat;
  churn_risk: MemberSnapshotStat;
}

export interface CoachTaskSnapshot {
  id: string;
  text: string;
  status: string;
}

export interface MorningBriefSnapshot {
  generated_for: string;
  source: SnapshotSource;
  coach_tasks: CoachTaskSnapshot[];
}

export type JourneyStageName = "new" | "building" | "recovering";

export interface JourneyStageEvidence {
  member_since: string;
  tenure_days: number;
  injury_node_ids: string[];
  injury_statuses: string[];
  workout_session_node_ids: string[];
  workout_session_count: number;
  completed_workout_count: number;
}

export interface JourneyStageSnapshot {
  stage: JourneyStageName;
  evidence: JourneyStageEvidence;
}

export interface MemberSnapshotPart {
  type: "data-member-snapshot";
  member_id: string;
  identity: MemberIdentity;
  stats: MemberSnapshotStats;
  morning_brief: MorningBriefSnapshot;
  journey_stage: JourneyStageSnapshot;
}
