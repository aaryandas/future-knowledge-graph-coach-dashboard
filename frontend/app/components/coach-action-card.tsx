import type {
  CoachTaskSnapshot,
  DataAction,
  DataActionPart,
  SessionPlanActionRow,
  WriteSessionPlan,
} from "@/lib/parts";

interface CoachActionCardProps {
  part: DataActionPart;
  currentCoachTask?: CoachTaskSnapshot | null;
}

interface DiffField {
  label: string;
  before: string;
  after: string;
}

interface SessionPlanRowChange {
  kind: "Added" | "Changed" | "Moved" | "Removed";
  rowId: string;
  exerciseId: string;
  fields: DiffField[];
}

const statusLabels: Record<DataAction["status"], string> = {
  pending: "Pending",
  confirmed: "Confirmed",
  discarded: "Discarded",
  failed: "Failed",
  blocked: "Blocked",
};

const sessionPlanRowFields: ReadonlyArray<{
  key: Exclude<keyof SessionPlanActionRow, "row_id">;
  label: string;
}> = [
  { key: "exercise_id", label: "Exercise" },
  { key: "section", label: "Section" },
  { key: "sets", label: "Sets" },
  { key: "reps", label: "Reps" },
  { key: "hold_minutes", label: "Hold (min)" },
  { key: "rest_minutes", label: "Rest (min)" },
  { key: "per_side", label: "Per side" },
  { key: "supports_weight", label: "Supports weight" },
  { key: "minutes", label: "Duration (min)" },
];

export function CoachActionCard({
  part,
  currentCoachTask = null,
}: CoachActionCardProps) {
  const { action, status } = part.data;
  const title = actionTitle(action.kind);

  return (
    <section
      className="coach-action-card"
      data-action-kind={action.kind}
      data-status={status}
      aria-label={`${statusLabels[status]} coach action: ${title}`}
    >
      <header className="coach-action-card-header">
        <h3>{title}</h3>
        <span className="coach-action-status">{statusLabels[status]}</span>
      </header>

      {action.kind === "send-member-message" ? (
        <div className="coach-action-message">
          <span>Full message</span>
          <blockquote>{action.message}</blockquote>
        </div>
      ) : action.kind === "update-brief-task" ? (
        <TaskUpdateDiff
          action={action}
          currentCoachTask={currentCoachTask}
        />
      ) : (
        <SessionPlanDiff action={action} />
      )}

      {status === "pending" ? (
        <footer
          className="coach-action-controls"
          aria-label={`${title} controls`}
        >
          <button type="button" aria-label={`Edit ${title.toLowerCase()}`}>
            Edit
          </button>
          <button type="button" aria-label={`Discard ${title.toLowerCase()}`}>
            Discard
          </button>
          <button
            type="button"
            className="coach-action-confirm"
            aria-label={`Confirm ${title.toLowerCase()}`}
          >
            Confirm
          </button>
        </footer>
      ) : null}
    </section>
  );
}

function TaskUpdateDiff({
  action,
  currentCoachTask,
}: {
  action: Extract<DataAction["action"], { kind: "update-brief-task" }>;
  currentCoachTask: CoachTaskSnapshot | null;
}) {
  const beforeText = currentCoachTask?.text ?? "Current value unavailable";
  const afterText = action.text ?? currentCoachTask?.text ?? "Unchanged";
  const fields: DiffField[] = [
    {
      label: "Task text",
      before: beforeText,
      after: afterText,
    },
    {
      label: "Status",
      before: currentCoachTask?.status ?? "Current value unavailable",
      after: action.status,
    },
  ];

  return (
    <div className="coach-action-task-diff">
      <p>
        <span>CoachTask</span>
        <strong>{action.coach_task_id}</strong>
      </p>
      <DiffTable label="Proposed CoachTask changes" fields={fields} />
    </div>
  );
}

function SessionPlanDiff({ action }: { action: WriteSessionPlan }) {
  const changes = sessionPlanChanges(action);
  const verdicts = new Map(
    action.verdicts.map((verdict) => [verdict.exercise_id, verdict.status]),
  );

  return (
    <div className="coach-action-plan-diff">
      <p className="coach-action-plan-id">
        <span>WorkoutSession</span>
        <strong>{action.session_id}</strong>
      </p>
      {changes.length === 0 ? (
        <p className="coach-action-no-changes">No row changes.</p>
      ) : (
        <div className="coach-action-plan-rows">
          {changes.map((change) => {
            const verdict = verdicts.get(change.exerciseId);
            return (
              <section key={change.rowId} className="coach-action-plan-row">
                <header>
                  <div>
                    <span>{change.kind}</span>
                    <h4>{change.rowId}</h4>
                  </div>
                  {verdict === undefined ? null : (
                    <span
                      className="coach-action-verdict"
                      data-verdict={verdict}
                    >
                      {verdict}
                    </span>
                  )}
                </header>
                <DiffTable
                  label={`${change.kind} session plan row ${change.rowId}`}
                  fields={change.fields}
                />
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function DiffTable({ label, fields }: { label: string; fields: DiffField[] }) {
  return (
    <div className="coach-action-diff" role="table" aria-label={label}>
      <div className="coach-action-diff-header" role="row">
        <span role="columnheader">Field</span>
        <span role="columnheader">Before</span>
        <span role="columnheader">After</span>
      </div>
      {fields.map((field) => (
        <div className="coach-action-diff-row" role="row" key={field.label}>
          <strong role="rowheader">{field.label}</strong>
          <del role="cell">{field.before}</del>
          <ins role="cell">{field.after}</ins>
        </div>
      ))}
    </div>
  );
}

function sessionPlanChanges(action: WriteSessionPlan): SessionPlanRowChange[] {
  const oldRows = new Map(action.old_rows.map((row) => [row.row_id, row]));
  const newRows = new Map(action.new_rows.map((row) => [row.row_id, row]));
  const rowIds = [
    ...action.old_rows.map((row) => row.row_id),
    ...action.new_rows
      .map((row) => row.row_id)
      .filter((rowId) => !oldRows.has(rowId)),
  ];

  return rowIds.flatMap((rowId): SessionPlanRowChange[] => {
    const before = oldRows.get(rowId);
    const after = newRows.get(rowId);
    if (before === undefined && after !== undefined) {
      return [
        {
          kind: "Added",
          rowId,
          exerciseId: after.exercise_id,
          fields: [
            positionField(null, action.new_rows.indexOf(after)),
            ...allRowFields(null, after),
          ],
        },
      ];
    }
    if (before !== undefined && after === undefined) {
      return [
        {
          kind: "Removed",
          rowId,
          exerciseId: before.exercise_id,
          fields: [
            positionField(action.old_rows.indexOf(before), null),
            ...allRowFields(before, null),
          ],
        },
      ];
    }
    if (before === undefined || after === undefined) {
      return [];
    }

    const oldPosition = action.old_rows.indexOf(before);
    const newPosition = action.new_rows.indexOf(after);
    const fields = sessionPlanRowFields.flatMap(({ key, label }) =>
      before[key] === after[key]
        ? []
        : [
            {
              label,
              before: formatRowValue(before[key]),
              after: formatRowValue(after[key]),
            },
          ],
    );
    if (oldPosition !== newPosition) {
      fields.unshift(positionField(oldPosition, newPosition));
    }
    if (fields.length === 0) {
      return [];
    }
    return [
      {
        kind:
          fields.length === 1 && oldPosition !== newPosition
            ? "Moved"
            : "Changed",
        rowId,
        exerciseId: after.exercise_id,
        fields,
      },
    ];
  });
}

function allRowFields(
  before: SessionPlanActionRow | null,
  after: SessionPlanActionRow | null,
): DiffField[] {
  return sessionPlanRowFields.map(({ key, label }) => ({
    label,
    before: formatRowValue(before?.[key] ?? null),
    after: formatRowValue(after?.[key] ?? null),
  }));
}

function positionField(
  beforeIndex: number | null,
  afterIndex: number | null,
): DiffField {
  return {
    label: "Position",
    before: beforeIndex === null ? "Not in plan" : String(beforeIndex + 1),
    after: afterIndex === null ? "Not in plan" : String(afterIndex + 1),
  };
}

function formatRowValue(
  value: SessionPlanActionRow[keyof SessionPlanActionRow],
): string {
  if (value === null) {
    return "Not set";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return String(value);
}

function actionTitle(kind: DataAction["action"]["kind"]): string {
  if (kind === "send-member-message") {
    return "Send member message";
  }
  if (kind === "update-brief-task") {
    return "Update brief task";
  }
  return "Update session plan";
}
