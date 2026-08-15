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
    <div className="graph-page workspace-enter">
      <header>
        <h1 className="page-heading">Graph</h1>
        <p className="page-subheading">
          See how Jordan’s context connects to movement and clinical knowledge.
        </p>
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
