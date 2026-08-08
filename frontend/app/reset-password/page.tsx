"use client";

import { ArrowLeft, CheckCircle2, CircleAlert, KeyRound, LoaderCircle } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { resetPassword } from "@/lib/api";

export default function ResetPasswordPage() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const resetToken = params.get("token") ?? "";
    setToken(resetToken);
    if (!resetToken) {
      setError("This reset link is missing a token.");
    }
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await resetPassword(token, password);
      setMessage(response.message);
      setPassword("");
      setConfirmPassword("");
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : "Unable to reset this password.");
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
            <h1>Choose Password</h1>
            <p>Set a new password for your VeinCAD CNC account.</p>
          </div>
        </div>

        <form className="loginForm" onSubmit={handleSubmit}>
          <label>
            <span>New password</span>
            <div className="inputWithIcon">
              <KeyRound size={18} />
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={6}
                autoComplete="new-password"
              />
            </div>
          </label>
          <label>
            <span>Confirm password</span>
            <div className="inputWithIcon">
              <KeyRound size={18} />
              <input
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
                minLength={6}
                autoComplete="new-password"
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

          <button
            className="primaryButton loginButton"
            type="submit"
            disabled={isSubmitting || !token || password.length < 6 || confirmPassword.length < 6}
          >
            {isSubmitting ? <LoaderCircle className="spin" size={18} /> : <KeyRound size={18} />}
            {isSubmitting ? "Resetting" : "Reset password"}
          </button>

          <a className="authBackLink" href="/">
            <ArrowLeft size={16} />
            Back to sign in
          </a>
        </form>
      </section>
    </main>
  );
}
