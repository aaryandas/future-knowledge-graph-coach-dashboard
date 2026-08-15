"use client";

import {
  Fragment,
  useState,
  type DragEvent,
  type KeyboardEvent,
} from "react";
import type {
  DataPlanPart,
  MemberSnapshotPart,
  PlanSectionName,
  Verdict,
} from "@/lib/parts";
import { useCopilotSidebar } from "./copilot-sidebar-context";
import {
  GripIcon,
  PencilIcon,
  PlusIcon,
  StarIcon,
  TrashIcon,
} from "./icons";

interface PlanEntry {
  id: string;
  section: PlanSectionName | null;
  sectionMinutes: number | null;
  verdict: Verdict | null;
  exercise: string;
  sets: string;
  reps: string;
  load: string;
  rest: string;
  notes: string;
}

type EditablePlanEntryField =
  | "exercise"
  | "sets"
  | "reps"
  | "load"
  | "rest"
  | "notes";

const seededPlanEntries: PlanEntry[] = [
  {
    id: "box-squat",
    section: null,
    sectionMinutes: null,
    verdict: null,
    exercise: "Box squat",
    sets: "3",
    reps: "8",
    load: "Bodyweight",
    rest: "90s",
    notes: "Comfortable range",
  },
  {
    id: "supported-split-squat",
    section: null,
    sectionMinutes: null,
    verdict: null,
    exercise: "Supported split squat",
    sets: "3",
    reps: "8 per side",
    load: "—",
    rest: "90s",
    notes: "Use support",
  },
  {
    id: "seated-hamstring-curl",
    section: null,
    sectionMinutes: null,
    verdict: null,
    exercise: "Seated hamstring curl",
    sets: "3",
    reps: "12",
    load: "Light",
    rest: "60s",
    notes: "Smooth control",
  },
  {
    id: "bike",
    section: null,
    sectionMinutes: null,
    verdict: null,
    exercise: "Bike",
    sets: "1",
    reps: "10 min",
    load: "Easy",
    rest: "—",
    notes: "Easy pace",
  },
];

const verdictLabels: Record<Verdict, string> = {
  clear: "Clear",
  caution: "Caution",
  exclude: "Exclude",
};

const planEntryFields: ReadonlyArray<{
  key: EditablePlanEntryField;
  label: string;
}> = [
  { key: "exercise", label: "Exercise" },
  { key: "sets", label: "Sets" },
  { key: "reps", label: "Reps" },
  { key: "load", label: "Load" },
  { key: "rest", label: "Rest" },
  { key: "notes", label: "Notes" },
];

export function MemberDashboard({
  part,
}: {
  part: MemberSnapshotPart | null;
}) {
  const { planPart, prefillMessage } = useCopilotSidebar();
  const [planEntries, setPlanEntries] = useState<PlanEntry[]>(() =>
    planEntriesFromPart(planPart),
  );
  const [previousPlanPart, setPreviousPlanPart] = useState(planPart);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const coachTask =
    part?.morning_brief.coach_tasks.find(({ status }) => status === "open") ??
    part?.morning_brief.coach_tasks[0] ??
    null;

  if (planPart !== previousPlanPart) {
    setPreviousPlanPart(planPart);
    setPlanEntries(planEntriesFromPart(planPart));
    setEditingId(null);
    setDraggingId(null);
    setConfirmed(false);
  }

  function updatePlanEntry(
    id: string,
    key: EditablePlanEntryField,
    value: string,
  ) {
    setPlanEntries((current) =>
      current.map((entry) =>
        entry.id === id ? { ...entry, [key]: value } : entry,
      ),
    );
    setConfirmed(false);
  }

  function removePlanEntry(id: string) {
    setPlanEntries((current) => current.filter((entry) => entry.id !== id));
    setEditingId((current) => (current === id ? null : current));
    setConfirmed(false);
  }

  function addPlanEntry() {
    const id = `plan-entry-${Date.now()}`;
    setPlanEntries((current) => {
      const lastEntry = current.at(-1);
      return [
        ...current,
        {
          id,
          section: lastEntry?.section ?? null,
          sectionMinutes: lastEntry?.sectionMinutes ?? null,
          verdict: null,
          exercise: "New exercise",
          sets: "",
          reps: "",
          load: "—",
          rest: "",
          notes: "",
        },
      ];
    });
    setEditingId(id);
    setConfirmed(false);
  }

  function movePlanEntry(sourceId: string, targetId: string) {
    if (sourceId === targetId) {
      return;
    }
    setPlanEntries((current) => {
      const sourceIndex = current.findIndex(({ id }) => id === sourceId);
      const targetIndex = current.findIndex(({ id }) => id === targetId);
      if (sourceIndex === -1 || targetIndex === -1) {
        return current;
      }
      const next = [...current];
      const [moved] = next.splice(sourceIndex, 1);
      if (moved === undefined) {
        return current;
      }
      next.splice(targetIndex, 0, moved);
      return next;
    });
    setConfirmed(false);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>, targetId: string) {
    event.preventDefault();
    const sourceId = draggingId ?? event.dataTransfer.getData("text/plain");
    if (sourceId) {
      movePlanEntry(sourceId, targetId);
    }
    setDraggingId(null);
  }

  function handleReorderKey(
    event: KeyboardEvent<HTMLButtonElement>,
    planEntryId: string,
  ) {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") {
      return;
    }
    event.preventDefault();
    const index = planEntries.findIndex(({ id }) => id === planEntryId);
    const targetIndex = event.key === "ArrowUp" ? index - 1 : index + 1;
    const target = planEntries[targetIndex];
    if (target) {
      movePlanEntry(planEntryId, target.id);
    }
  }

  return (
    <div className="member-dashboard workspace-enter">
      <section className="morning-brief" aria-labelledby="morning-brief-title">
        <StarIcon className="morning-brief-icon" />
        <h1 id="morning-brief-title">Morning brief</h1>
        <p>
          {coachTask?.text ?? "No CoachTasks for today"}
          {part?.morning_brief.source.stale ? (
            <span className="morning-brief-age">
              {formatAge(part.morning_brief.source.age_days)} old
            </span>
          ) : null}
        </p>
        <button
          type="button"
          disabled={coachTask === null}
          onClick={() =>
            prefillMessage(`Draft a note for this CoachTask: ${coachTask?.text ?? ""}`)
          }
        >
          Send note
        </button>
      </section>

      <section className="session-card" aria-labelledby="session-title">
        <div className="session-card-body">
          <div className="session-heading">
            <h2 id="session-title" className="display-title session-title">
              Today’s session
            </h2>
            {planPart === null ? null : (
              <div className="session-plan-timing" aria-label="Session timing">
                <strong>{formatMinutes(planPart.data.packed_minutes)} packed</strong>
                <span>{formatMinutes(planPart.data.requested_minutes)} requested</span>
              </div>
            )}
          </div>

          <div
            className="session-table"
            role="table"
            aria-label="Today’s session exercises"
          >
            <div className="session-table-header" role="row">
              <span aria-hidden="true" />
              {planEntryFields.map(({ label }) => (
                <span key={label} role="columnheader">
                  {label}
                </span>
              ))}
              <span className="sr-only" role="columnheader">
                Actions
              </span>
            </div>

            <div className="session-table-body" role="rowgroup">
              {planEntries.map((entry, index) => {
                const editing = entry.id === editingId;
                const section = entry.section;
                const startsSection =
                  section !== null &&
                  planEntries[index - 1]?.section !== section;
                return (
                  <Fragment key={entry.id}>
                    {startsSection && section !== null ? (
                      <div className="session-section-row" role="row">
                        <div
                          className="session-section-label"
                          role="cell"
                          aria-colspan={8}
                        >
                          <h3>{sectionLabel(section)}</h3>
                          {entry.sectionMinutes === null ? null : (
                            <span>{formatMinutes(entry.sectionMinutes)}</span>
                          )}
                        </div>
                      </div>
                    ) : null}
                    <div
                      className="session-row"
                      role="row"
                      data-dragging={draggingId === entry.id}
                      data-editing={editing}
                      data-verdict={entry.verdict ?? undefined}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event) => handleDrop(event, entry.id)}
                    >
                      <button
                        type="button"
                        className="row-grabber"
                        draggable={!editing}
                        aria-label={`Move ${entry.exercise}. Use arrow keys to reorder.`}
                        onDragStart={(event) => {
                          setDraggingId(entry.id);
                          event.dataTransfer.setData("text/plain", entry.id);
                          event.dataTransfer.effectAllowed = "move";
                        }}
                        onDragEnd={() => setDraggingId(null)}
                        onKeyDown={(event) => handleReorderKey(event, entry.id)}
                      >
                        <GripIcon className="size-5" />
                      </button>

                      {planEntryFields.map(({ key, label }) => (
                        <div
                          key={key}
                          className={
                            key === "exercise"
                              ? "session-cell session-exercise-cell"
                              : "session-cell"
                          }
                          role="cell"
                          data-label={label}
                        >
                          {key === "exercise" && entry.verdict !== null ? (
                            <span
                              className="session-verdict"
                              data-verdict={entry.verdict}
                            >
                              {verdictLabels[entry.verdict]}
                            </span>
                          ) : null}
                          {editing ? (
                            <input
                              aria-label={`${label} for ${entry.exercise}`}
                              value={entry[key]}
                              onChange={(event) =>
                                updatePlanEntry(entry.id, key, event.target.value)
                              }
                            />
                          ) : (
                            <span>{entry[key]}</span>
                          )}
                        </div>
                      ))}

                      <div className="session-row-actions" role="cell">
                        <button
                          type="button"
                          className="row-action"
                          aria-label={
                            editing
                              ? `Finish editing ${entry.exercise}`
                              : `Edit ${entry.exercise}`
                          }
                          onClick={() => setEditingId(editing ? null : entry.id)}
                        >
                          {editing ? (
                            <span>Done</span>
                          ) : (
                            <PencilIcon className="size-[18px]" />
                          )}
                        </button>
                        <button
                          type="button"
                          className="row-action"
                          aria-label={`Remove ${entry.exercise}`}
                          onClick={() => removePlanEntry(entry.id)}
                        >
                          <TrashIcon className="size-[18px]" />
                        </button>
                      </div>
                    </div>
                  </Fragment>
                );
              })}
            </div>
          </div>

          <button type="button" className="add-exercise" onClick={addPlanEntry}>
            <PlusIcon className="size-[18px]" />
            Add exercise
          </button>
        </div>

        <footer className="session-footer">
          <span className="sr-only" role="status" aria-live="polite">
            {confirmed ? "Session confirmed" : "Session has unconfirmed changes"}
          </span>
          <button
            type="button"
            className="confirm-session"
            disabled={confirmed}
            onClick={() => setConfirmed(true)}
          >
            {confirmed ? "Confirmed" : "Confirm session"}
          </button>
        </footer>
      </section>
    </div>
  );
}

function planEntriesFromPart(part: DataPlanPart | null): PlanEntry[] {
  if (part === null) {
    return seededPlanEntries;
  }
  const sections = [part.data.warm_up, part.data.main, part.data.cool_down];
  return sections.flatMap(({ entries, minutes, section }) =>
    entries.map((entry, index) => ({
      id: `${section}:${entry.exercise_id}:${index}`,
      section,
      sectionMinutes: minutes,
      verdict: entry.verdict,
      exercise: entry.name,
      sets: String(entry.sets),
      reps:
        entry.reps === null
          ? formatMinutes(entry.hold_minutes)
          : `${entry.reps}${entry.per_side ? " per side" : ""}`,
      load: entry.supports_weight ? "Weighted" : "Bodyweight",
      rest: formatMinutes(entry.rest_minutes),
      notes: entry.caution_note ?? "",
    })),
  );
}

function sectionLabel(section: PlanSectionName): string {
  if (section === "warm-up") {
    return "Warm-up";
  }
  if (section === "cool-down") {
    return "Cool-down";
  }
  return "Main";
}

function formatMinutes(value: number | null): string {
  if (value === null) {
    return "—";
  }
  if (value < 1) {
    return `${Math.round(value * 60)}s`;
  }
  return `${value} min`;
}

function formatAge(days: number): string {
  if (days < 14) {
    return `${days}d`;
  }
  if (days < 60) {
    return `${Math.floor(days / 7)}w`;
  }
  if (days < 730) {
    return `${Math.floor(days / 30.4375)}mo`;
  }
  return `${Math.floor(days / 365.25)}y`;
}
