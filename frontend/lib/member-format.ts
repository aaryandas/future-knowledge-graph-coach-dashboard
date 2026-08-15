import type { MemberIdentityInjury } from "./parts";

export function formatInjury(injury: MemberIdentityInjury | null): string {
  if (injury === null) {
    return "No active MemberInjury";
  }
  return [injury.region, injury.finding, injury.status].filter(Boolean).join(" · ");
}
