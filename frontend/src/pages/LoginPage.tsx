import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate } from "react-router";

import { ApiError } from "../api/client";
import { homeFor, useAuth } from "../auth/AuthContext";

function errorKey(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) return "login.errors.invalid";
  if (error instanceof ApiError && error.status === 429) return "login.errors.tooMany";
  return "login.errors.generic";
}

export function LoginPage() {
  const { t } = useTranslation();
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to={homeFor(user)} replace />;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const signedIn = await signIn(email, password);
      navigate(homeFor(signedIn), { replace: true });
    } catch (caught) {
      setError(errorKey(caught));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="card login" onSubmit={handleSubmit}>
      <h1>{t("login.title")}</h1>
      <label>
        {t("login.email")}
        <input
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </label>
      <label>
        {t("login.password")}
        <input
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      {error && <p role="alert">{t(error)}</p>}
      <button type="submit" disabled={submitting}>
        {t("login.submit")}
      </button>
    </form>
  );
}
