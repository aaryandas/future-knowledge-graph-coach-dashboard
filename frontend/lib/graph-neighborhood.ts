import "server-only";

import type { GraphNeighborhoodPart } from "@/lib/parts";

export async function getGraphNeighborhood(
  memberId: string,
): Promise<GraphNeighborhoodPart | null> {
  const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(
      `${backend}/api/members/${encodeURIComponent(memberId)}/graph-neighborhood`,
      { cache: "no-store" },
    );
    if (!response.ok) {
      return null;
    }
    const part = (await response.json()) as GraphNeighborhoodPart;
    if (part.type !== "data-graph-neighborhood") {
      return null;
    }
    return part;
  } catch {
    return null;
  }
}
