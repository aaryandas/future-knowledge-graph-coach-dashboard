"use client";

import Link from "next/link";
import { Popover } from "@base-ui/react/popover";
import type { JourneyStageSnapshot } from "@/lib/parts";

export function JourneyStageChip({
  journeyStage,
}: {
  journeyStage: JourneyStageSnapshot;
}) {
  const { evidence } = journeyStage;

  return (
    <Popover.Root>
      <Popover.Trigger className="journey-chip press">
        <span>Journey stage</span>
        <strong>{journeyStage.stage}</strong>
        <span aria-hidden="true">⌄</span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner sideOffset={8} align="start" className="journey-positioner">
          <Popover.Popup className="journey-popover glass">
            <Popover.Title>Journey stage evidence</Popover.Title>
            <dl>
              <div>
                <dt>Tenure</dt>
                <dd>{formatTenure(evidence.tenure_days)}</dd>
              </div>
              <div>
                <dt>MemberInjury</dt>
                <dd>
                  {evidence.injury_statuses.length === 0
                    ? "none"
                    : evidence.injury_statuses.join(" · ")}
                </dd>
              </div>
              <div>
                <dt>WorkoutSession</dt>
                <dd>
                  {evidence.completed_workout_count} / {evidence.workout_session_count}
                  {" completed"}
                </dd>
              </div>
            </dl>
            <Link href="/graph" className="journey-graph-link press">
              Graph view <span aria-hidden="true">→</span>
            </Link>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}

function formatTenure(days: number): string {
  if (days < 60) {
    return `${days} days`;
  }
  const months = Math.floor(days / 30.4375);
  if (months < 24) {
    return `${months} months`;
  }
  const years = Math.floor(months / 12);
  const remainingMonths = months % 12;
  return remainingMonths === 0
    ? `${years} years`
    : `${years} years · ${remainingMonths} months`;
}
