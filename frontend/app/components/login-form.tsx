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
        value="coach@future.co"
        readOnly
        className="login-input"
      />
      <label className="sr-only" htmlFor="password">
        Password
      </label>
      <input
        id="password"
        name="password"
        type="password"
        value="futurecoach"
        readOnly
        className="login-input"
      />
      <button className={buttonVariants({ className: "login-submit w-full" })} type="submit">
        Sign in
      </button>
    </form>
  );
}
