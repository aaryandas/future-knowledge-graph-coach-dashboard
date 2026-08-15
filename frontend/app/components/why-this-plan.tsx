import type {
  DataConstraintsPart,
  DataPlanPart,
  DataTracePart,
  PackingTraceEvent,
  PlanEntry,
  PlanSectionName,
  TraceEvent,
} from "@/lib/parts";

type WhyPlanKind = "removed" | "replaced" | "capped" | "unrecognized";

interface WhyPlanItem {
  kind: WhyPlanKind;
  sentence: string;
}

export function WhyThisPlan({
  planPart,
  tracePart,
  constraintsPart,
}: {
  planPart: DataPlanPart | null;
  tracePart: DataTracePart | null;
  constraintsPart: DataConstraintsPart | null;
}) {
  if (planPart === null || tracePart === null || constraintsPart === null) {
    return null;
  }

  const items = whyPlanItems(planPart, tracePart, constraintsPart);

  return (
    <section className="why-plan-card" aria-labelledby="why-plan-title">
      <h2 id="why-plan-title" className="display-title">
        Why this plan
      </h2>
      {items.length === 0 ? (
        <p className="why-plan-empty">
          The session fits the current request without changes.
        </p>
      ) : (
        <ul>
          {items.map((item, index) => (
            <li key={`${item.kind}-${index}`} data-kind={item.kind}>
              <span className="why-plan-marker" aria-hidden="true" />
              <p>{item.sentence}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function whyPlanItems(
  planPart: DataPlanPart,
  tracePart: DataTracePart,
  constraintsPart: DataConstraintsPart,
): WhyPlanItem[] {
  const entriesById = planEntriesById(planPart);
  const events = tracePart.data;
  const items: WhyPlanItem[] = [];

  items.push(...removedItems(events, constraintsPart));
  items.push(...replacementItems(events));
  items.push(...cappedItems(events, planPart, entriesById));
  items.push(
    ...constraintsPart.data.omissions.map(({ raw_text: rawText }) => ({
      kind: "unrecognized" as const,
      sentence: `Unrecognized term “${rawText}” was not used.`,
    })),
  );

  return items;
}

function removedItems(
  events: TraceEvent[],
  constraintsPart: DataConstraintsPart,
): WhyPlanItem[] {
  const items: WhyPlanItem[] = constraintsPart.data.constraints.exclusions
    .filter(({ enforced }) => enforced)
    .map(({ raw_text: rawText }) => ({
      kind: "removed" as const,
      sentence: `Removed “${rawText}” from the session.`,
    }));
  const filtered = events
    .filter(isPackingTraceEvent)
    .filter((event) => event.action === "filtered");
  const safetyCount = filtered.filter((event) =>
    event.reason.toLowerCase().includes("safety verdict"),
  ).length;
  const equipmentCount = filtered.filter((event) =>
    event.reason.toLowerCase().includes("equipment"),
  ).length;

  if (safetyCount > 0) {
    items.push({
      kind: "removed",
      sentence: `Removed ${countedExercises(safetyCount)} that did not meet the member’s safety constraints.`,
    });
  }
  if (equipmentCount > 0) {
    items.push({
      kind: "removed",
      sentence: `Removed ${countedExercises(equipmentCount)} that need unavailable equipment.`,
    });
  }

  return items;
}

function replacementItems(events: TraceEvent[]): WhyPlanItem[] {
  return events
    .filter((event) => event.kind === "substitution")
    .map((event) => {
      const names = event.reason.match(/^Replaced (.+) with (.+) by shared /);
      const sentence =
        names === null
          ? `Replaced one exercise with a suitable option based on ${event.basis}.`
          : `Replaced ${names[1]} with ${names[2]} because they share ${withArticle(event.basis)}.`;
      return { kind: "replaced" as const, sentence };
    });
}

function cappedItems(
  events: TraceEvent[],
  planPart: DataPlanPart,
  entriesById: Map<string, PlanEntry>,
): WhyPlanItem[] {
  const cutEvents = events
    .filter(isPackingTraceEvent)
    .filter((event) => event.action === "cut");
  const reducedEntries = cutEvents.flatMap((event) => {
    if (!event.reason.toLowerCase().includes("reduced main sets")) {
      return [];
    }
    const entry = entriesById.get(event.exercise_id);
    return entry === undefined ? [] : [entry];
  });
  const droppedSections = new Set<PlanSectionName>();
  for (const event of cutEvents) {
    if (
      !event.reason.toLowerCase().includes("reduced main sets") &&
      event.section !== null
    ) {
      droppedSections.add(event.section);
    }
  }
  const items = reducedEntries.map((entry) => ({
    kind: "capped" as const,
    sentence: `Capped ${entry.name} at ${entry.sets} ${plural(entry.sets, "set")} to keep the session within ${planPart.data.requested_minutes} minutes.`,
  }));

  for (const section of droppedSections) {
    items.push({
      kind: "capped",
      sentence: `Capped the session at ${planPart.data.requested_minutes} minutes by removing lower-ranked ${sectionLabel(section)} work.`,
    });
  }

  return items;
}

function planEntriesById(planPart: DataPlanPart): Map<string, PlanEntry> {
  return new Map(
    [
      ...planPart.data.warm_up.entries,
      ...planPart.data.main.entries,
      ...planPart.data.cool_down.entries,
    ].map((entry) => [entry.exercise_id, entry]),
  );
}

function isPackingTraceEvent(event: TraceEvent): event is PackingTraceEvent {
  return event.kind === "packing";
}

function countedExercises(count: number): string {
  return count === 1 ? "one exercise" : `${count} exercises`;
}

function withArticle(value: string): string {
  return value === "movement pattern" ? "a movement pattern" : "muscle overlap";
}

function sectionLabel(section: PlanSectionName): string {
  return section === "cool-down" ? "cool-down" : section;
}

function plural(value: number, noun: string): string {
  return value === 1 ? noun : `${noun}s`;
}
