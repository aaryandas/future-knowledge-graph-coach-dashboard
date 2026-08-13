"use client";

import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { buttonVariants } from "@/lib/theme";

export function LoginForm() {
  const router = useRouter();

  function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    router.push("/member");
  }

  return (
    <form onSubmit={signIn}>
      <label className="sr-only" htmlFor="email">
        Email
      </label>
      <input
        id="email"
        name="email"
        type="email"
        value="sam@ridgeline.coach"
        readOnly
        className="mb-2.5 w-full rounded-xl border border-border-strong bg-surface px-3 py-2.5 text-foreground outline-none"
      />
      <label className="sr-only" htmlFor="password">
        Password
      </label>
      <input
        id="password"
        name="password"
        type="password"
        value="ridgeline"
        readOnly
        className="mb-2.5 w-full rounded-xl border border-border-strong bg-surface px-3 py-2.5 text-foreground outline-none"
      />
      <button className={buttonVariants({ className: "w-full" })} type="submit">
        Sign in
      </button>
    </form>
  );
}
