import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Graph",
};

export default function GraphPage() {
  return (
    <div className="workspace-enter mx-auto max-w-[1100px]">
      <header className="mb-3">
        <h1 className="text-[19px] font-semibold tracking-[-0.02em]">
          Graph view
        </h1>
        <p className="mt-0.5 text-xs text-foreground-subtle">
          Movement/Clinical Graph (KG1) and Jordan&apos;s Member Context Graph (KG2).
        </p>
      </header>

      <section
        className="glass grid min-h-[480px] place-items-center rounded-[20px] p-[18px]"
        aria-labelledby="graph-workspace-title"
      >
        <div className="max-w-sm text-center">
          <div
            className="mx-auto mb-5 grid size-20 place-items-center rounded-full border border-border bg-surface"
            aria-hidden="true"
          >
            <div className="relative size-9">
              <span className="absolute top-0 left-0 size-2.5 rounded-full bg-accent" />
              <span className="absolute right-0 bottom-0 size-2.5 rounded-full bg-data-blue" />
              <span className="absolute bottom-0 left-1 size-2.5 rounded-full bg-warning" />
              <span className="absolute top-[17px] left-[17px] size-1.5 rounded-full bg-foreground-muted" />
            </div>
          </div>
          <h2 id="graph-workspace-title" className="text-[15px] font-semibold">
            Graph workspace
          </h2>
          <p className="mt-1 text-xs leading-5 text-foreground-subtle">
            Member context and traced Movement/Clinical Graph relationships render in this workspace.
          </p>
        </div>
      </section>
    </div>
  );
}
