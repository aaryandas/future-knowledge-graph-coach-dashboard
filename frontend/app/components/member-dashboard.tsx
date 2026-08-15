"use client";

import { useState, type DragEvent, type KeyboardEvent } from "react";
import type { MemberSnapshotPart } from "@/lib/parts";
import { useCopilotSidebar } from "./copilot-sidebar-context";
import {
  GripIcon,
  PencilIcon,
  PlusIcon,
  StarIcon,
  TrashIcon,
} from "./icons";

interface SessionExercise {
  id: string;
  exercise: string;
  sets: string;
  reps: string;
  load: string;
  rest: string;
  notes: string;
}

const initialExercises: SessionExercise[] = [
  {
    id: "box-squat",
    exercise: "Box squat",
    sets: "3",
    reps: "8",
    load: "Bodyweight",
    rest: "90s",
    notes: "Comfortable range",
  },
  {
    id: "supported-split-squat",
    exercise: "Supported split squat",
    sets: "3",
    reps: "8 per side",
    load: "—",
    rest: "90s",
    notes: "Use support",
  },
  {
    id: "seated-hamstring-curl",
    exercise: "Seated hamstring curl",
    sets: "3",
    reps: "12",
    load: "Light",
    rest: "60s",
    notes: "Smooth control",
  },
  {
    id: "bike",
    exercise: "Bike",
    sets: "1",
    reps: "10 min",
    load: "Easy",
    rest: "—",
    notes: "Easy pace",
  },
];

const exerciseFields: ReadonlyArray<{
  key: keyof Omit<SessionExercise, "id">;
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
  const { prefillMessage } = useCopilotSidebar();
  const [exercises, setExercises] = useState(initialExercises);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const coachTask =
    part?.morning_brief.coach_tasks.find(({ status }) => status === "open") ??
    part?.morning_brief.coach_tasks[0] ??
    null;

  function updateExercise(
    id: string,
    key: keyof Omit<SessionExercise, "id">,
    value: string,
  ) {
    setExercises((current) =>
      current.map((exercise) =>
        exercise.id === id ? { ...exercise, [key]: value } : exercise,
      ),
    );
    setConfirmed(false);
  }

  function removeExercise(id: string) {
    setExercises((current) => current.filter((exercise) => exercise.id !== id));
    setEditingId((current) => (current === id ? null : current));
    setConfirmed(false);
  }

  function addExercise() {
    const id = `exercise-${Date.now()}`;
    setExercises((current) => [
      ...current,
      {
        id,
        exercise: "New exercise",
        sets: "3",
        reps: "8",
        load: "—",
        rest: "60s",
        notes: "",
      },
    ]);
    setEditingId(id);
    setConfirmed(false);
  }

  function moveExercise(sourceId: string, targetId: string) {
    if (sourceId === targetId) {
      return;
    }
    setExercises((current) => {
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
      moveExercise(sourceId, targetId);
    }
    setDraggingId(null);
  }

  function handleReorderKey(
    event: KeyboardEvent<HTMLButtonElement>,
    exerciseId: string,
  ) {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") {
      return;
    }
    event.preventDefault();
    const index = exercises.findIndex(({ id }) => id === exerciseId);
    const targetIndex = event.key === "ArrowUp" ? index - 1 : index + 1;
    const target = exercises[targetIndex];
    if (target) {
      moveExercise(exerciseId, target.id);
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
          <h2 id="session-title" className="display-title session-title">
            Today’s session
          </h2>

          <div className="session-table" role="table" aria-label="Today’s session exercises">
            <div className="session-table-header" role="row">
              <span aria-hidden="true" />
              {exerciseFields.map(({ label }) => (
                <span key={label} role="columnheader">
                  {label}
                </span>
              ))}
              <span className="sr-only" role="columnheader">
                Actions
              </span>
            </div>

            <div className="session-table-body" role="rowgroup">
              {exercises.map((exercise) => {
                const editing = exercise.id === editingId;
                return (
                  <div
                    key={exercise.id}
                    className="session-row"
                    role="row"
                    data-dragging={draggingId === exercise.id}
                    data-editing={editing}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => handleDrop(event, exercise.id)}
                  >
                    <button
                      type="button"
                      className="row-grabber"
                      draggable={!editing}
                      aria-label={`Move ${exercise.exercise}. Use arrow keys to reorder.`}
                      onDragStart={(event) => {
                        setDraggingId(exercise.id);
                        event.dataTransfer.setData("text/plain", exercise.id);
                        event.dataTransfer.effectAllowed = "move";
                      }}
                      onDragEnd={() => setDraggingId(null)}
                      onKeyDown={(event) => handleReorderKey(event, exercise.id)}
                    >
                      <GripIcon className="size-5" />
                    </button>

                    {exerciseFields.map(({ key, label }) => (
                      <div key={key} className="session-cell" role="cell" data-label={label}>
                        {editing ? (
                          <input
                            aria-label={`${label} for ${exercise.exercise}`}
                            value={exercise[key]}
                            onChange={(event) =>
                              updateExercise(exercise.id, key, event.target.value)
                            }
                          />
                        ) : (
                          exercise[key]
                        )}
                      </div>
                    ))}

                    <div className="session-row-actions" role="cell">
                      <button
                        type="button"
                        className="row-action"
                        aria-label={editing ? `Finish editing ${exercise.exercise}` : `Edit ${exercise.exercise}`}
                        onClick={() => setEditingId(editing ? null : exercise.id)}
                      >
                        {editing ? <span>Done</span> : <PencilIcon className="size-[18px]" />}
                      </button>
                      <button
                        type="button"
                        className="row-action"
                        aria-label={`Remove ${exercise.exercise}`}
                        onClick={() => removeExercise(exercise.id)}
                      >
                        <TrashIcon className="size-[18px]" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <button type="button" className="add-exercise" onClick={addExercise}>
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
