import { JourneyStageChip } from "./journey-stage-chip";
import type {
  MemberSnapshotPart,
  MemberSnapshotStat,
  SnapshotTrend,
} from "@/lib/parts";

const statDefinitions = [
  { key: "adherence", label: "Adherence" },
  { key: "sleep", label: "Sleep · 7d avg" },
  { key: "sessions", label: "Sessions · wk" },
  { key: "churn_risk", label: "Churn risk" },
] as const;

const trendMarkers: Record<SnapshotTrend, string> = {
  up: "↑",
  down: "↓",
  flat: "→",
};

export function MemberSnapshot({
  part,
}: {
  part: MemberSnapshotPart | null;
}) {
  if (part === null) {
    return (
      <div className="member-snapshot-state glass" role="status">
        Member snapshot is unavailable.
      </div>
    );
  }

  const { identity, stats, morning_brief: morningBrief } = part;

  return (
    <div className="member-snapshot workspace-enter">
      <header className="member-identity" aria-label="Member identity">
        <h1>{identity.name}</h1>
        <JourneyStageChip journeyStage={part.journey_stage} />
        <IdentityChip>{identity.tier}</IdentityChip>
        <IdentityChip>
          {identity.age} · {identity.sex}
        </IdentityChip>
        <IdentityChip>since {formatMonth(identity.member_since)}</IdentityChip>
        {identity.injury === null ? null : (
          <span className="member-injury-flag">
            {[
              identity.injury.region,
              identity.injury.finding,
              identity.injury.status,
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        )}
        {identity.goals.map((goal) => (
          <IdentityChip key={goal.id}>
            <span className="identity-chip-key">goal</span>
            {goal.text}
          </IdentityChip>
        ))}
      </header>

      <section className="member-stat-grid" aria-label="Member stats">
        {statDefinitions.map(({ key, label }) => (
          <StatTile key={key} label={label} stat={stats[key]} />
        ))}
      </section>

      <section className="morning-brief glass" aria-labelledby="morning-brief-title">
        <div className="morning-brief-heading">
          <h2 id="morning-brief-title">Morning brief</h2>
          {morningBrief.source.stale ? (
            <StaleAge days={morningBrief.source.age_days} />
          ) : null}
        </div>
        {morningBrief.coach_tasks.length === 0 ? (
          <p className="morning-brief-empty">No CoachTasks</p>
        ) : (
          <ul>
            {morningBrief.coach_tasks.map((task) => (
              <li key={task.id} data-status={task.status}>
                <span aria-hidden="true" />
                <p>{task.text}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function IdentityChip({ children }: { children: React.ReactNode }) {
  return <span className="identity-chip">{children}</span>;
}

function StatTile({
  label,
  stat,
}: {
  label: string;
  stat: MemberSnapshotStat;
}) {
  return (
    <article
      className="member-stat-tile glass"
      data-stale={stat.source?.stale || undefined}
    >
      <div className="member-stat-label">
        <h2>{label}</h2>
        {stat.source?.stale ? <StaleAge days={stat.source.age_days} /> : null}
      </div>
      <p className="member-stat-value">
        {stat.value ?? "—"}
        {stat.suffix === null ? null : <small>{stat.suffix}</small>}
      </p>
      <p className="member-stat-trend" data-trend={stat.trend}>
        <span aria-hidden="true">{trendMarkers[stat.trend]}</span>
        <span>{stat.trend_text}</span>
      </p>
    </article>
  );
}

function StaleAge({ days }: { days: number }) {
  return <span className="stale-age">{formatAge(days)} old</span>;
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

function formatMonth(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function MemberSnapshotSkeleton() {
  return (
    <div className="member-snapshot" aria-hidden="true">
      <div className="member-identity-skeleton">
        <div className="skeleton-shimmer" />
        <div className="skeleton-shimmer" />
        <div className="skeleton-shimmer" />
        <div className="skeleton-shimmer" />
      </div>
      <div className="member-stat-grid">
        {statDefinitions.map(({ key }) => (
          <div key={key} className="member-stat-tile glass">
            <div className="skeleton-shimmer member-skeleton-label" />
            <div className="skeleton-shimmer member-skeleton-value" />
            <div className="skeleton-shimmer member-skeleton-trend" />
          </div>
        ))}
      </div>
      <div className="morning-brief glass member-brief-skeleton">
        <div className="skeleton-shimmer" />
        <div className="skeleton-shimmer" />
      </div>
    </div>
  );
}
