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
import { GenerationNotices } from "./generation-notices";
import {
  AdjustIcon,
  GripIcon,
  PencilIcon,
  PlusIcon,
  ShieldIcon,
  StarIcon,
  TrashIcon,
} from "./icons";
import { WhyThisPlan } from "./why-this-plan";

interface PlanEntry {
  id: string;
  section: PlanSectionName | null;
  sectionMinutes: number | null;
  verdict: Verdict | null;
  exercise: string;
  sets: string;
  reps: string;
  rest: string;
  notes: string;
}

type EditableDoseField = "sets" | "reps" | "rest";

const verdictLabels: Record<Verdict, string> = {
  clear: "Clear",
  caution: "Caution",
  exclude: "Exclude",
};

export function MemberDashboard({
  part,
}: {
  part: MemberSnapshotPart | null;
}) {
  const {
    planPart,
    tracePart,
    constraintsPart,
    adjustmentBusy,
    prefillMessage,
    submitAdjustment,
  } = useCopilotSidebar();
  const [planEntries, setPlanEntries] = useState<PlanEntry[]>(() =>
    planEntriesFromPart(planPart),
  );
  const [previousPlanPart, setPreviousPlanPart] = useState(planPart);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const latestSession = part?.latest_session ?? null;
  const hasGeneratedPlan = planPart !== null;
  const sessionEntries = hasGeneratedPlan
    ? planEntries
    : sessionEntriesFromSnapshot(part);
  const sessionTitle = hasGeneratedPlan
    ? "Today’s session"
    : (latestSession?.title ?? "Latest session");
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
    key: EditableDoseField,
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

  function applyDose(entry: PlanEntry) {
    submitAdjustment(composeEditDoseAdjustment(entry));
    setEditingId(null);
    setConfirmed(false);
  }

  function swapExercise(entry: PlanEntry) {
    submitAdjustment(composeSwapAdjustment(entry));
    setConfirmed(false);
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

      <GenerationNotices
        part={constraintsPart}
        adjustmentBusy={adjustmentBusy}
        onSubmitAdjustment={submitAdjustment}
      />

      <section
        className="session-card"
        aria-labelledby="session-title"
        data-generated-plan={hasGeneratedPlan}
      >
        <div className="session-card-body">
          <div className="session-heading">
            <h2 id="session-title" className="display-title session-title">
              {sessionTitle}
            </h2>
            {planPart === null && latestSession !== null ? (
              <div className="session-plan-timing" aria-label="Session details">
                <strong>{formatMinutes(latestSession.duration_min)}</strong>
                <span>{latestSession.date}</span>
              </div>
            ) : planPart === null ? null : (
              <div className="session-plan-timing" aria-label="Session timing">
                <strong>{formatMinutes(planPart.data.packed_minutes)} packed</strong>
                <span>{formatMinutes(planPart.data.requested_minutes)} requested</span>
              </div>
            )}
          </div>

          <div
            className="session-table"
            role="table"
            aria-label={`${sessionTitle} exercises`}
            data-generated-plan={hasGeneratedPlan}
          >
            <div className="session-table-header" role="row">
              {hasGeneratedPlan ? <span aria-hidden="true" /> : null}
              <span role="columnheader">
                {hasGeneratedPlan ? "Exercise and dose" : "Exercise"}
              </span>
              {hasGeneratedPlan ? <span role="columnheader">Actions</span> : null}
            </div>

            <div className="session-table-body" role="rowgroup">
              {sessionEntries.map((entry, index) => {
                const editing = entry.id === editingId;
                const section = entry.section;
                const startsSection =
                  section !== null &&
                  sessionEntries[index - 1]?.section !== section;
                return (
                  <Fragment key={entry.id}>
                    {startsSection && section !== null ? (
                      <div className="session-section-row" role="row">
                        <div
                          className="session-section-label"
                          role="cell"
                          aria-colspan={3}
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
                      {hasGeneratedPlan ? (
                        <>
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

                          <div className="session-entry" role="cell">
                            <div className="session-entry-title">
                              {entry.verdict === null ? null : (
                                <span
                                  className="session-verdict"
                                  data-verdict={entry.verdict}
                                  title={`${verdictLabels[entry.verdict]} verdict`}
                                >
                                  <ShieldIcon className="size-4" />
                                  <span className="sr-only">
                                    {verdictLabels[entry.verdict]} verdict
                                  </span>
                                </span>
                              )}
                              <strong>{entry.exercise}</strong>
                            </div>

                            {editing ? (
                              <div className="session-dose-editor">
                                {(["sets", "reps", "rest"] as const).map(
                                  (field) => (
                                    <label key={field}>
                                      <span>{doseFieldLabel(field)}</span>
                                      <input
                                        aria-label={`${doseFieldLabel(field)} for ${entry.exercise}`}
                                        value={entry[field]}
                                        onChange={(event) =>
                                          updatePlanEntry(
                                            entry.id,
                                            field,
                                            event.target.value,
                                          )
                                        }
                                      />
                                    </label>
                                  ),
                                )}
                              </div>
                            ) : (
                              <p className="session-dose">{formatDose(entry)}</p>
                            )}
                            {entry.notes === "" ? null : (
                              <p className="session-caution-note">
                                {entry.notes}
                              </p>
                            )}
                          </div>

                          <div className="session-row-actions" role="cell">
                            <button
                              type="button"
                              className="session-adjustment"
                              disabled={adjustmentBusy}
                              onClick={() =>
                                editing
                                  ? applyDose(entry)
                                  : setEditingId(entry.id)
                              }
                            >
                              <PencilIcon className="size-4" />
                              {editing ? "Apply dose" : "Edit dose"}
                            </button>
                            <button
                              type="button"
                              className="session-adjustment"
                              disabled={adjustmentBusy || editing}
                              onClick={() => swapExercise(entry)}
                            >
                              <AdjustIcon className="size-4" />
                              Swap
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
                        </>
                      ) : (
                        <div className="session-entry" role="cell">
                          <strong>{entry.exercise}</strong>
                        </div>
                      )}
                    </div>
                  </Fragment>
                );
              })}
            </div>
          </div>

          {hasGeneratedPlan ? (
            <button type="button" className="add-exercise" onClick={addPlanEntry}>
              <PlusIcon className="size-[18px]" />
              Add exercise
            </button>
          ) : null}
        </div>

        {hasGeneratedPlan ? (
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
        ) : null}
      </section>

      <WhyThisPlan
        planPart={planPart}
        tracePart={tracePart}
        constraintsPart={constraintsPart}
      />
    </div>
  );
}

function planEntriesFromPart(part: DataPlanPart | null): PlanEntry[] {
  if (part === null) {
    return [];
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
          ? `${formatMinutes(entry.hold_minutes)} hold${entry.per_side ? " per side" : ""}`
          : `${entry.reps} reps${entry.per_side ? " per side" : ""}`,
      rest: formatMinutes(entry.rest_minutes),
      notes: entry.caution_note ?? "",
    })),
  );
}

function sessionEntriesFromSnapshot(part: MemberSnapshotPart | null): PlanEntry[] {
  return (part?.latest_session?.exercises ?? []).map((exercise, index) => ({
    id: `latest-session:${index}`,
    section: null,
    sectionMinutes: null,
    verdict: null,
    exercise,
    sets: "",
    reps: "",
    rest: "",
    notes: "",
  }));
}

export function composeEditDoseAdjustment(
  entry: Pick<PlanEntry, "exercise" | "sets" | "reps" | "rest">,
): string {
  return `Adjust ${entry.exercise} to ${entry.sets} sets, ${entry.reps}, with ${entry.rest} rest.`;
}

export function composeSwapAdjustment(
  entry: Pick<PlanEntry, "exercise" | "section">,
): string {
  if (entry.section === null) {
    return `Swap ${entry.exercise} for a suitable alternative.`;
  }
  return `Swap ${entry.exercise} for a suitable alternative in the ${sectionLabel(entry.section)} section.`;
}

function formatDose(entry: PlanEntry): string {
  return `${entry.sets} ${entry.sets === "1" ? "set" : "sets"} · ${entry.reps} · ${entry.rest} rest`;
}

function doseFieldLabel(field: EditableDoseField): string {
  if (field === "reps") {
    return "Reps or hold";
  }
  return field[0]?.toUpperCase() + field.slice(1);
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
