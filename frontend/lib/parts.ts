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

export interface AgentTraceEvent {
  kind: "agent";
  action: "annotation";
  reason: string;
  used: string[];
  wasGeneratedBy: "annotate";
  wasAttributedTo: "agent";
}

export type TraceEvent =
  | ResolutionTraceEvent
  | VerdictTraceEvent
  | PackingTraceEvent
  | AgentTraceEvent
  | SubstitutionTraceEvent;

export interface DataTracePart {
  type: "data-trace";
  data: TraceEvent[];
}

export interface ConstraintsData {
  targets: ResolvedMention[];
  constraints: ConstraintSet;
  omissions: OmissionChip[];
  not_enforced: NotEnforcedFlag[];
  session_injury_persistence_suggestions: SessionInjuryPersistenceSuggestion[];
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

export interface LatestSessionSnapshot {
  title: string;
  date: string;
  duration_min: number;
  rpe: number | null;
  exercises: string[];
}

export interface MemberSnapshotPart {
  type: "data-member-snapshot";
  member_id: string;
  identity: MemberIdentity;
  stats: MemberSnapshotStats;
  latest_session: LatestSessionSnapshot | null;
  morning_brief: MorningBriefSnapshot;
  journey_stage: JourneyStageSnapshot;
}

export interface Barrier {
  node_id: string;
  kind: string;
  copper_id: string;
  reason: string;
  risk_level: string;
  evidence_node_ids: string[];
}

export interface CoachTask {
  node_id: string;
  generated_for: string;
  type: string;
  text: string;
  status: string;
  addressed_node_ids: string[];
}

export interface DataBrief {
  generated_for: string;
  churn_risk_level: string;
  churn_risk_reasons: string[];
  barriers: Barrier[];
  coach_tasks: CoachTask[];
}

export interface DataBriefPart {
  type: "data-brief";
  data: DataBrief;
}

export interface SendMemberMessage {
  kind: "send-member-message";
  message: string;
  coach_task_id?: string | null;
}

export interface UpdateBriefTask {
  kind: "update-brief-task";
  coach_task_id: string;
  status: "open" | "completed" | "dismissed";
  text?: string | null;
}

export interface SessionPlanActionRow {
  row_id: string;
  exercise_id: string;
  section: PlanSectionName | null;
  sets: number | null;
  reps: number | null;
  hold_minutes: number | null;
  rest_minutes: number | null;
  per_side: boolean | null;
  supports_weight: boolean | null;
  minutes: number | null;
}

export interface AddSessionPlanRow {
  kind: "add";
  row: SessionPlanActionRow;
  position: number;
}

export interface EditSessionPlanRow {
  kind: "edit";
  row: SessionPlanActionRow;
}

export interface ReorderSessionPlanRow {
  kind: "reorder";
  row_id: string;
  position: number;
}

export interface RemoveSessionPlanRow {
  kind: "remove";
  row_id: string;
}

export type SessionPlanEdit =
  | AddSessionPlanRow
  | EditSessionPlanRow
  | ReorderSessionPlanRow
  | RemoveSessionPlanRow;

export interface SessionPlanVerdict {
  exercise_id: string;
  status: Verdict;
  trace: VerdictTraceEvent[];
}

export interface SessionPlanEditFailure {
  reason:
    | "session-not-found"
    | "row-not-found"
    | "duplicate-row-id"
    | "position-out-of-range";
  edit_index: number | null;
  row_id: string | null;
}

export interface WriteSessionPlan {
  kind: "write-session-plan";
  session_id: string;
  edits: SessionPlanEdit[];
  old_rows: SessionPlanActionRow[];
  new_rows: SessionPlanActionRow[];
  verdicts: SessionPlanVerdict[];
  failure: SessionPlanEditFailure | null;
}

export type CoachAction =
  | SendMemberMessage
  | UpdateBriefTask
  | WriteSessionPlan;

export interface DataAction {
  action_id: string;
  status: "pending" | "confirmed" | "discarded" | "failed" | "blocked";
  action: CoachAction;
  actor: string | null;
  timestamp: string | null;
}

export interface DataActionPart {
  type: "data-action";
  data: DataAction;
}

export interface CoachActionResolution {
  decision: "confirm" | "discard";
  action?: CoachAction;
}

export type ChatDataParts = {
  plan: Plan;
  trace: TraceEvent[];
  constraints: ConstraintsData;
  chart: DataChart;
  sources: DataSources;
  brief: DataBrief;
  action: DataAction;
};

export type DashboardMessage = UIMessage<unknown, ChatDataParts>;

export type TypedDataPart =
  | DataPlanPart
  | DataTracePart
  | DataConstraintsPart
  | DataChartPart
  | DataSourcesPart
  | GraphNeighborhoodPart
  | MemberSnapshotPart
  | DataBriefPart
  | DataActionPart
  | DataPart;

export type ChartKind =
  | "adherence_trend"
  | "sleep_week"
  | "message_pattern"
  | "four_week_comparison";

export type ChartWindow = "7-days" | "28-days";

export interface CategoryAxis {
  label: string;
  values: string[];
}

export interface NumericAxis {
  label: string;
  unit: string;
  minimum: number;
  maximum: number;
  ticks: number[];
}

export interface ChartAxes {
  x: CategoryAxis;
  y: NumericAxis;
}

export interface AdherenceTrendPoint {
  observed_at: string;
  completion_percent: number;
  observation_node_id: string;
}

export interface SleepWeekPoint {
  observed_at: string;
  hours: number;
  observation_node_id: string;
}

export interface MessagePatternPoint {
  date: string;
  member_count: number;
  coach_count: number;
  observation_node_id: string;
}

export interface FourWeekComparisonPoint {
  week_of: string;
  completion_percent: number;
  observation_node_id: string;
}

interface ChartBase {
  axes: ChartAxes;
  observation_node_ids: string[];
}

export interface AdherenceTrendChart extends ChartBase {
  kind: "adherence_trend";
  window: ChartWindow;
  series: AdherenceTrendPoint[];
}

export interface SleepWeekChart extends ChartBase {
  kind: "sleep_week";
  window: "7-days";
  series: SleepWeekPoint[];
}

export interface MessagePatternChart extends ChartBase {
  kind: "message_pattern";
  window: ChartWindow;
  series: MessagePatternPoint[];
}

export interface FourWeekComparisonChart extends ChartBase {
  kind: "four_week_comparison";
  window: "28-days";
  series: FourWeekComparisonPoint[];
}

export type DataChart =
  | AdherenceTrendChart
  | SleepWeekChart
  | MessagePatternChart
  | FourWeekComparisonChart;

export interface DataChartPart {
  type: "data-chart";
  data: DataChart;
}

export interface OmissionChip {
  raw_text: string;
  purpose: "target" | "exclusion" | "equipment override";
  candidates: ResolutionCandidate[];
  message: string;
}

export interface NotEnforcedFlag {
  raw_text: string;
  purpose: "session injury";
  candidates: ResolutionCandidate[];
  message: string;
}

export interface SessionInjuryPersistenceSuggestion {
  raw_text: string;
  concept_id: string;
  vocabulary: "Joint" | "AnatomicalStructure" | "ClinicalFinding";
  action: "persist session injury";
  requires_confirmation: true;
  message: string;
}

export interface SubstitutionTraceEvent {
  kind: "substitution";
  dropped_exercise_id: string;
  replacement_exercise_id: string;
  basis: "movement pattern" | "muscle overlap";
  shared_movement_pattern_ids: string[];
  shared_muscle_group_ids: string[];
  reason: string;
  used: string[];
  wasGeneratedBy: "pair_substitutions";
  wasAttributedTo: "graph";
}
