import type { Metadata } from "next";
import { MemberDashboard } from "@/app/components/member-dashboard";

export const metadata: Metadata = {
  title: "Dashboard",
};

export default function MemberPage() {
  return <MemberDashboard />;
}
