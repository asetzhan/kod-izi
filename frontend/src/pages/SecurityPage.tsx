import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate } from "react-router";

import { apiSend } from "../api/client";
import { homeFor, needsSecondFactor, useAuth } from "../auth/AuthContext";
import { ErrorText } from "../components/Status";

interface Setup {
  secret: string;
  otpauth_uri: string;
}

/** Spec 14.1: teachers and administrators set up a TOTP second factor. */
export function SecurityPage() {
  const { t } = useTranslation();
  const { user, signOut } = useAuth();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);

  if (user === null) return <Navigate to="/login" replace />;
  if (!needsSecondFactor(user)) return <Navigate to={homeFor(user)} replace />;

  const start = async () => {
    setError(null);
    try {
      setSetup(await apiSend<Setup>("POST", "/api/auth/2fa/setup"));
    } catch (caught) {
      setError(caught);
    }
  };

  const enable = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await apiSend("POST", "/api/auth/2fa/enable", { code, password });
      // Sessions opened with the password alone are revoked: sign in again with a code.
      await signOut();
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <section className="card">
      <h1>{t("security.title")}</h1>
      <p>{t("security.why")}</p>
      {!setup ? (
        <button type="button" onClick={start}>
          {t("security.start")}
        </button>
      ) : (
        <form className="inline-form" onSubmit={enable}>
          <p>{t("security.addKey")}</p>
          <p>
            <code className="secret">{setup.secret}</code>
          </p>
          <p className="muted">
            <a href={setup.otpauth_uri}>{t("security.openApp")}</a>
          </p>
          <label>
            {t("security.code")}
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </label>
          <label>
            {t("security.password")}
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <p className="muted">{t("security.signInAgain")}</p>
          <button type="submit">{t("security.enable")}</button>
        </form>
      )}
      {error !== null && <ErrorText error={error} />}
    </section>
  );
}
