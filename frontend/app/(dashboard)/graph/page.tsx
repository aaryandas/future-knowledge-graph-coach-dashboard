import type { Metadata } from "next";
import { GraphView } from "@/app/components/graph-view";

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
      <GraphView memberId="mbr_01HX9JORDAN" />
    </div>
  );
}
