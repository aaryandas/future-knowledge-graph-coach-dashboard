import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Members",
};

export default function MembersPage() {
  return (
    <div className="members-page workspace-enter">
      <header>
        <h1 className="page-heading">Members</h1>
        <p className="page-subheading">
          Open a member workspace to review today’s signal and session.
        </p>
      </header>
      <section className="member-list" aria-label="Members">
        <article className="member-list-row">
          <div>
            <strong>Jordan Rivera</strong>
            <span>41 · Lower-body strength</span>
          </div>
          <div>
            <strong>Recovering</strong>
            <span>Left-knee PFPS</span>
          </div>
          <div>
            <strong>50% adherence</strong>
            <span>Previous period 100%</span>
          </div>
          <Link href="/member">Open dashboard</Link>
        </article>
      </section>
    </div>
  );
}
