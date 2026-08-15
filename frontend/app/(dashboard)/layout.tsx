import type { ReactNode } from "react";
import { AppShell } from "@/app/components/app-shell";
import { getMemberSnapshot } from "@/lib/member-snapshot";

const memberId = "mbr_01HX9JORDAN";

export default async function DashboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  const memberSnapshot = await getMemberSnapshot(memberId);
  return <AppShell memberSnapshot={memberSnapshot}>{children}</AppShell>;
}
