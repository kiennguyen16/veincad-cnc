"use client";

import { ArrowLeft, CheckCircle2, CircleAlert, LoaderCircle, Mail } from "lucide-react";
import Link from "next/link";
import { type FormEvent, useState } from "react";
import { requestPasswordReset } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setIsSubmitting(true);

    try {
      const response = await requestPasswordReset(email.trim());
      setMessage(response.message);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to request a password reset.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="loginShell">
      <section className="loginPanel">
        <div className="loginBrand">
          <div className="brandMark" aria-hidden="true">
            <img className="brandLogo" src="/stone-logo.png" alt="" />
          </div>
          <div>
            <h1>Reset Password</h1>
            <p>Enter your email and we will send a reset link.</p>
          </div>
        </div>

        <form className="loginForm" onSubmit={handleSubmit}>
          <label>
            <span>Email</span>
            <div className="inputWithIcon">
              <Mail size={18} />
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
              />
            </div>
          </label>

          {message && (
            <div className="authMessage success" role="status">
              <CheckCircle2 size={18} />
              <span>{message}</span>
            </div>
          )}

          {error && (
            <div className="alert compact" role="alert">
              <CircleAlert size={18} />
              <span>{error}</span>
            </div>
          )}

          <button className="primaryButton loginButton" type="submit" disabled={isSubmitting || !email.trim()}>
            {isSubmitting ? <LoaderCircle className="spin" size={18} /> : <Mail size={18} />}
            {isSubmitting ? "Sending" : "Send reset link"}
          </button>

          <Link className="authBackLink" href="/">
            <ArrowLeft size={16} />
            Back to sign in
          </Link>
        </form>
      </section>
    </main>
  );
}
