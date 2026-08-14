import type { Metadata } from "next";
import { LoginForm } from "@/app/components/login-form";
import { RidgelineMark } from "@/app/components/ridgeline-mark";

export const metadata: Metadata = {
  title: "Sign in",
};

export default function LoginPage() {
  return (
    <main className="screen-enter grid min-h-svh place-items-center px-5 py-10">
      <section
        className="glass w-full max-w-[330px] rounded-[22px] p-[30px]"
        aria-labelledby="login-title"
      >
        <RidgelineMark className="mb-5 size-8" />
        <h1
          id="login-title"
          className="text-[22px] font-semibold tracking-[-0.02em]"
        >
          Ridgeline
        </h1>
        <p className="mt-0.5 mb-[22px] text-[12.5px] text-foreground-subtle">
          Coach console
        </p>
        <LoginForm />
        <p className="mt-4 text-center text-[11px] text-foreground-subtle">
          Demo access · no credentials required
        </p>
      </section>
    </main>
  );
}
