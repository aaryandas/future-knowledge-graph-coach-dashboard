import type {
  DataPlanPart,
  PlanEntry,
  PlanSection,
  Verdict,
} from "@/lib/parts";

const verdictMarkers: Record<Verdict, string> = {
  clear: "✓",
  caution: "▲",
  exclude: "×",
};

export function SessionPlan({ part }: { part: DataPlanPart }) {
  const plan = part.data;
  const sections = [plan.warm_up, plan.main, plan.cool_down];

  return (
    <section className="session-plan glass" aria-labelledby="session-plan-title">
      <header className="session-plan-heading">
        <div>
          <span>Today&apos;s session</span>
          <h2 id="session-plan-title">
            {formatMinutes(plan.packed_minutes)} min
          </h2>
        </div>
        <p>{plan.requested_minutes} min requested</p>
      </header>
      <div className="session-plan-sections">
        {sections.map((section) => (
          <SessionSection key={section.section} section={section} />
        ))}
      </div>
    </section>
  );
}

function SessionSection({ section }: { section: PlanSection }) {
  return (
    <section
      className="session-plan-section"
      aria-labelledby={`plan-${section.section}`}
    >
      <div className="session-plan-section-heading">
        <h3 id={`plan-${section.section}`}>{sectionLabel(section.section)}</h3>
        <span>{formatMinutes(section.minutes)} min</span>
      </div>
      <ul>
        {section.entries.map((entry) => (
          <PlanRow key={entry.exercise_id} entry={entry} />
        ))}
      </ul>
    </section>
  );
}

function PlanRow({ entry }: { entry: PlanEntry }) {
  return (
    <li className="session-plan-row" data-verdict={entry.verdict}>
      <span
        className="session-plan-verdict"
        aria-label={`${entry.verdict} verdict`}
        title={`${entry.verdict} verdict`}
      >
        {verdictMarkers[entry.verdict]}
      </span>
      <div>
        <strong>
          {entry.name}
          {entry.per_side ? <small> · each side</small> : null}
        </strong>
        <p>{formatDose(entry)}</p>
        {entry.caution_note === null ? null : (
          <span className="session-plan-caution">{entry.caution_note}</span>
        )}
      </div>
    </li>
  );
}

function formatDose(entry: PlanEntry): string {
  const dose =
    entry.reps === null
      ? `${entry.sets} ${plural(entry.sets, "hold")} · ${formatClock(entry.hold_minutes ?? 0)} each`
      : `${entry.sets} ${plural(entry.sets, "set")} · ${entry.reps} reps`;
  return entry.rest_minutes > 0
    ? `${dose} · ${formatClock(entry.rest_minutes)} rest`
    : dose;
}

function formatClock(minutes: number): string {
  const wholeMinutes = Math.floor(minutes);
  const seconds = Math.round((minutes - wholeMinutes) * 60);
  return `${wholeMinutes}:${seconds.toString().padStart(2, "0")}`;
}

function formatMinutes(minutes: number): string {
  return Number.isInteger(minutes) ? String(minutes) : minutes.toFixed(1);
}

function sectionLabel(section: PlanSection["section"]): string {
  if (section === "warm-up") {
    return "Warm-up";
  }
  if (section === "cool-down") {
    return "Cool-down";
  }
  return "Main";
}

function plural(value: number, noun: string): string {
  return value === 1 ? noun : `${noun}s`;
}
