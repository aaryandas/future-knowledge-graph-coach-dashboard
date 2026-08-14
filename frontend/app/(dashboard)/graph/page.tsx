import type { Metadata } from "next";
import { Suspense } from "react";
import { GraphSkeleton, GraphView } from "@/app/components/graph-view";
import { getGraphNeighborhood } from "@/lib/graph-neighborhood";

const memberId = "mbr_01HX9JORDAN";

export const metadata: Metadata = {
  title: "Graph",
};

export default function GraphPage() {
  return (
    <div className="workspace-enter mx-auto max-w-[1100px]">
      <header className="mb-2.5">
        <h1 className="text-[19px] font-semibold tracking-[-0.02em]">
          Graph view
        </h1>
      </header>
      <Suspense fallback={<GraphSkeleton />}>
        <GraphNeighborhood />
      </Suspense>
    </div>
  );
}

async function GraphNeighborhood() {
  const part = await getGraphNeighborhood(memberId);
  return <GraphView part={part} />;
}
