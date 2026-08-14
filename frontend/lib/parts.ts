import type { UIMessage } from "@ai-sdk/react";

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface Source {
  tool: string;
  node_ids: string[];
}

export interface DataSources {
  sources: Source[];
}

export interface DataSourcesPart {
  type: "data-sources";
  data: DataSources;
}

export interface DataPart {
  type: string;
  data: JsonValue;
}

export type ResolutionPurpose =
  | "target"
  | "exclusion"
  | "session injury"
  | "equipment override";

export type ResolutionVocabulary =
  | "Exercise"
  | "MuscleGroup"
  | "Joint"
  | "Equipment"
  | "AnatomicalStructure"
  | "ClinicalFinding";

export type ResolverPass = "exact" | "fuzzy" | "vector" | "none";

export interface ResolutionCandidate {
  concept_id: string;
  preferred_term: string;
  confidence: number;
}

export interface ResolvedMention {
  purpose: ResolutionPurpose;
  vocabulary: ResolutionVocabulary;
  raw_text: string;
  concept_id: string | null;
  confidence: number;
  pass: ResolverPass;
  candidates: ResolutionCandidate[];
  modifiers: string[];
  enforced: boolean;
  message: string | null;
}

export interface ConstraintSet {
  exclusions: ResolvedMention[];
  session_injuries: ResolvedMention[];
  equipment_override: ResolvedMention[] | null;
}

export type GenerationFailureReason =
  | "llm-unavailable"
  | "provider-error"
  | "invalid-output"
  | "member-not-found"
  | "empty-section"
  | "minimum-plan-exceeds-window";

export type PlanSectionName = "warm-up" | "main" | "cool-down";
export type Verdict = "exclude" | "caution" | "clear";

export interface GenerationFailure {
  reason: GenerationFailureReason;
  message: string;
  section: PlanSectionName | null;
  attempts: number | null;
}

export interface PlanEntry {
  exercise_id: string;
  name: string;
  sets: number;
  reps: number | null;
  hold_minutes: number | null;
  rest_minutes: number;
  per_side: boolean;
  supports_weight: boolean;
  verdict: Verdict;
  caution_note: string | null;
  minutes: number;
}

export interface PlanSection {
  section: PlanSectionName;
  entries: PlanEntry[];
  minutes: number;
}

export interface Plan {
  warm_up: PlanSection;
  main: PlanSection;
  cool_down: PlanSection;
  requested_minutes: number;
  packed_minutes: number;
}

export interface DataPlanPart {
  type: "data-plan";
  data: Plan;
}

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
  | "clinicalDirective"
  | "evidencedBy"
  | "addresses";

export interface WalkedNode {
  node_id: string;
  kind: GraphNodeKind;
  name: string | null;
}

export interface WalkedEdge {
  edge_id: string;
  kind: GraphEdgeKind;
  source_id: string;
  target_id: string;
}

export interface WalkedPath {
  nodes: WalkedNode[];
  edges: WalkedEdge[];
}

export interface ResolutionTraceEvent {
  kind: "resolution";
  purpose: ResolutionPurpose;
  vocabulary: ResolutionVocabulary;
  raw_text: string;
  concept_id: string | null;
  confidence: number;
  pass: ResolverPass;
  candidates: ResolutionCandidate[];
  modifiers: string[];
  enforced: boolean;
  reason: string;
  used: string[];
  wasGeneratedBy: "resolve";
  wasAttributedTo: "graph";
}

export interface VerdictTraceEvent {
  kind: "verdict";
  exercise_id: string;
  status: Verdict;
  layer:
    | "clinical directive"
    | "contraindication"
    | "SNOMED anatomical fallback"
    | null;
  reason: string;
  walked_path: WalkedPath;
  used: string[];
  wasGeneratedBy: "evaluate_safety";
  wasAttributedTo: "graph" | "agent";
}

export interface PackingTraceEvent {
  kind: "packing";
  action: "filtered" | "selected" | "cut";
  section: PlanSectionName | null;
  exercise_id: string;
  reason: string;
  used: string[];
  score: number | null;
  wasGeneratedBy: "pack";
  wasAttributedTo: "graph";
}

export type TraceEvent =
  | ResolutionTraceEvent
  | VerdictTraceEvent
  | PackingTraceEvent;

export interface DataTracePart {
  type: "data-trace";
  data: TraceEvent[];
}

export interface ConstraintsData {
  targets: ResolvedMention[];
  constraints: ConstraintSet;
  failure: GenerationFailure | null;
}

export interface DataConstraintsPart {
  type: "data-constraints";
  data: ConstraintsData;
}

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

export type ChatDataParts = {
  plan: Plan;
  trace: TraceEvent[];
  constraints: ConstraintsData;
  sources: DataSources;
  chart: JsonValue;
  brief: JsonValue;
  action: JsonValue;
};

export type DashboardMessage = UIMessage<unknown, ChatDataParts>;

export type TypedDataPart =
  | DataPlanPart
  | DataTracePart
  | DataConstraintsPart
  | DataSourcesPart
  | GraphNeighborhoodPart
  | MemberSnapshotPart
  | DataPart;
