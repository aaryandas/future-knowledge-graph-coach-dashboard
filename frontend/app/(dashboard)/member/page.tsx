import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Member",
};

const memberFacts = ["1:1 coaching", "41 · she/her", "since Sep 2024"];

export default function MemberPage() {
  return (
    <div className="workspace-enter">
      <header className="mb-4 flex flex-wrap items-center gap-3.5">
        <h1 className="text-[19px] font-semibold tracking-[-0.02em]">
          Jordan Rivera
        </h1>
        {memberFacts.map((fact) => (
          <span
            key={fact}
            className="rounded-full border border-border bg-surface px-2.5 py-1 text-[11.5px] text-foreground-muted"
          >
            {fact}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5 rounded-full bg-warning-muted px-2.5 py-1 text-[11.5px] font-medium text-warning">
          <span className="size-1.5 rounded-full bg-warning" aria-hidden="true" />
          left knee · PFPS · recovering
        </span>
      </header>

      <section aria-labelledby="member-overview-title">
        <div className="mb-3 flex items-baseline justify-between gap-4">
          <div>
            <h2 id="member-overview-title" className="text-[15px] font-semibold">
              Member overview
            </h2>
            <p className="mt-0.5 text-xs text-foreground-subtle">
              Current coaching context and plan activity.
            </p>
          </div>
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-foreground-subtle">
            Updated now
          </span>
        </div>

        <div className="mb-3 grid grid-cols-2 gap-2.5 lg:grid-cols-4" aria-hidden="true">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="glass rounded-2xl p-3.5">
              <div className="skeleton-shimmer h-2 w-16 rounded-full bg-surface-raised" />
              <div className="skeleton-shimmer mt-3 h-6 w-20 rounded-md bg-surface-raised" />
              <div className="skeleton-shimmer mt-2 h-2 w-24 max-w-full rounded-full bg-surface" />
            </div>
          ))}
        </div>

        <div className="glass min-h-[360px] rounded-[18px] p-4" aria-hidden="true">
          <div className="flex items-center justify-between border-b border-border pb-4">
            <div className="skeleton-shimmer h-3 w-40 rounded-full bg-surface-raised" />
            <div className="skeleton-shimmer h-7 w-20 rounded-full bg-surface" />
          </div>
          <div className="space-y-4 py-5">
            {[88, 72, 81, 64].map((width) => (
              <div key={width} className="flex items-center gap-3">
                <div className="skeleton-shimmer size-7 shrink-0 rounded-full bg-surface-raised" />
                <div
                  className="skeleton-shimmer h-3 rounded-full bg-surface-raised"
                  style={{ width: `${width}%` }}
                />
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
