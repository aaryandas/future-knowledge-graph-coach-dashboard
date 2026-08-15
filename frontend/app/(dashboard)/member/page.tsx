import type { Metadata } from "next";
import { Suspense } from "react";
import { MemberDashboard } from "@/app/components/member-dashboard";
import { getMemberSnapshot } from "@/lib/member-snapshot";

const memberId = "mbr_01HX9JORDAN";

export const metadata: Metadata = {
  title: "Dashboard",
};

export default function MemberPage() {
  return (
    <Suspense fallback={<MemberDashboard part={null} />}>
      <MemberOverview />
    </Suspense>
  );
}

async function MemberOverview() {
  const part = await getMemberSnapshot(memberId);
  return <MemberDashboard part={part} />;
}
