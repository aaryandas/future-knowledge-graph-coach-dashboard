import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { formatInjury } from "@/lib/member-format";
import type { MemberSnapshotPart, MemberSnapshotStat } from "@/lib/parts";
import { getMemberSnapshot } from "@/lib/member-snapshot";

const memberId = "mbr_01HX9JORDAN";

export const metadata: Metadata = {
  title: "Members",
};

export default function MembersPage() {
  return (
    <Suspense fallback={<MemberList part={null} />}>
      <MemberOverview />
    </Suspense>
  );
}

async function MemberOverview() {
  const part = await getMemberSnapshot(memberId);
  return <MemberList part={part} />;
}

function MemberList({ part }: { part: MemberSnapshotPart | null }) {
  const identity = part?.identity ?? null;
  const injury = identity?.injury ?? null;
  const goal = identity?.goals[0] ?? null;

  return (
    <div className="members-page workspace-enter">
      <header>
        <h1 className="page-heading">Members</h1>
        <p className="page-subheading">
          Open a member workspace to review today’s signal and session.
        </p>
      </header>
      <section className="member-list" aria-label="Members">
        <article className="member-list-row">
          <div>
            <strong>{identity?.name ?? "Member unavailable"}</strong>
            <span>
              {identity === null ? "Profile unavailable" : identity.age}
              {goal === null ? "" : ` · ${goal.text}`}
            </span>
          </div>
          <div>
            <strong>{formatJourneyStage(part)}</strong>
            <span>{formatInjury(injury)}</span>
          </div>
          <div>
            <strong>{formatStat("Adherence", part?.stats.adherence ?? null)}</strong>
            <span>{part?.stats.adherence.trend_text ?? "Trend unavailable"}</span>
          </div>
          <Link href="/member">Open dashboard</Link>
        </article>
      </section>
    </div>
  );
}

function formatJourneyStage(part: MemberSnapshotPart | null): string {
  const stage = part?.journey_stage.stage;
  return stage === undefined
    ? "Journey stage unavailable"
    : `${stage.charAt(0).toUpperCase()}${stage.slice(1)}`;
}

function formatStat(label: string, stat: MemberSnapshotStat | null): string {
  if (stat?.value === null || stat === null) {
    return `${label} unavailable`;
  }
  return `${label} ${stat.value}${stat.suffix ?? ""}`;
}
