import "server-only";

import type { MemberSnapshotPart } from "@/lib/parts";

export async function getMemberSnapshot(
  memberId: string,
): Promise<MemberSnapshotPart | null> {
  const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(
      `${backend}/api/members/${encodeURIComponent(memberId)}/snapshot`,
      { cache: "no-store" },
    );
    if (!response.ok) {
      return null;
    }
    const part = (await response.json()) as MemberSnapshotPart;
    if (part.type !== "data-member-snapshot") {
      return null;
    }
    return part;
  } catch {
    return null;
  }
}
