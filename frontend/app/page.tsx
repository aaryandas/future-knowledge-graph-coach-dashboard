import type { Metadata } from "next";
import { LoginForm } from "@/app/components/login-form";

export const metadata: Metadata = {
  title: "Sign in",
};

export default function LoginPage() {
  return (
    <main className="login-screen screen-enter">
      <section className="login-introduction" aria-labelledby="login-title">
        <p className="login-eyebrow">Future Coach</p>
        <h1 id="login-title" className="display-title">
          Start with what matters today.
        </h1>
        <p>
          Review the signal, shape the session, and keep each member moving
          forward.
        </p>
      </section>
      <section className="login-card" aria-label="Sign in">
        <div>
          <h2 className="display-title">Welcome back</h2>
          <p>Sign in to your coaching workspace.</p>
        </div>
        <LoginForm />
        <p className="login-demo-note">Demo access · no credentials required</p>
      </section>
    </main>
  );
}
