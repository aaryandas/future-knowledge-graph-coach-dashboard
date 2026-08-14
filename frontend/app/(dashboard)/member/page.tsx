import type { Metadata } from "next";
import { Suspense } from "react";
import {
  MemberSnapshot,
  MemberSnapshotSkeleton,
} from "@/app/components/member-snapshot";
import { getMemberSnapshot } from "@/lib/member-snapshot";

const memberId = "mbr_01HX9JORDAN";

export const metadata: Metadata = {
  title: "Member",
};

export default function MemberPage() {
  return (
    <Suspense fallback={<MemberSnapshotSkeleton />}>
      <MemberOverview />
    </Suspense>
  );
}

async function MemberOverview() {
  const part = await getMemberSnapshot(memberId);
  return <MemberSnapshot part={part} />;
}
