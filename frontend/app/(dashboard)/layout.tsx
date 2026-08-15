import type { ReactNode } from "react";
import { AppShell } from "@/app/components/app-shell";
import { getCopilotHistory } from "@/lib/copilot-history";
import { getMemberSnapshot } from "@/lib/member-snapshot";

const memberId = "mbr_01HX9JORDAN";

export default async function DashboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  const [memberSnapshot, initialCopilotMessages] = await Promise.all([
    getMemberSnapshot(memberId),
    getCopilotHistory(memberId),
  ]);
  return (
    <AppShell
      memberSnapshot={memberSnapshot}
      initialCopilotMessages={initialCopilotMessages}
    >
      {children}
    </AppShell>
  );
}
