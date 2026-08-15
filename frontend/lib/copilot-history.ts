import "server-only";

import type { CopilotHistory, DashboardMessage } from "@/lib/parts";

export async function getCopilotHistory(
  memberId: string,
): Promise<DashboardMessage[]> {
  const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(
      `${backend}/api/members/${encodeURIComponent(memberId)}/copilot/history`,
      { cache: "no-store" },
    );
    if (!response.ok) {
      return [];
    }
    const history = (await response.json()) as CopilotHistory;
    if (history.id !== memberId || !Array.isArray(history.messages)) {
      return [];
    }
    return history.messages;
  } catch {
    return [];
  }
}
