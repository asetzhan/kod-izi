import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate } from "react-router";

import { apiSend } from "../api/client";
import { homeFor, useAuth } from "../auth/AuthContext";
import { useResource } from "../api/useResource";
import { ErrorText, Status } from "../components/Status";

interface Consent {
  version: string;
  accepted_version: string | null;
  accepted_at: string | null;
  withdrawn_at: string | null;
}

/** Spec 13, 14.3: consent to data processing; AI-assisted assessment is announced. */
export function ConsentPage() {
  const { t } = useTranslation();
  const { user, refreshUser } = useAuth();
  const consent = useResource<Consent>("/api/consent");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState(false);

  if (user === null) return <Navigate to="/login" replace />;
  if (done) return <Navigate to={homeFor(user)} replace />;
  if (!consent.data) return <Status loading={consent.loading} error={consent.error} />;
  const active =
    consent.data.accepted_version === consent.data.version && !consent.data.withdrawn_at;

  const accept = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await apiSend("POST", "/api/consent", { version: consent.data?.version });
      await refreshUser?.();
      setDone(true);
    } catch (caught) {
      setError(caught);
    }
  };

  const withdraw = async () => {
    try {
      await apiSend("POST", "/api/consent/withdraw");
      await refreshUser?.();
      consent.reload();
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <section className="card consent">
      <h1>{t("consent.title")}</h1>
      <p>{t("consent.what")}</p>
      <p>
        <strong>{t("consent.ai")}</strong>
      </p>
      <p>{t("consent.llm")}</p>
      <p>{t("consent.storage")}</p>
      <p>{t("consent.rights")}</p>
      <p className="muted">{t("consent.version", { version: consent.data.version })}</p>
      {active ? (
        <>
          <p role="status">{t("consent.given")}</p>
          <button type="button" onClick={withdraw}>
            {t("consent.withdraw")}
          </button>
        </>
      ) : (
        <form className="inline-form" onSubmit={accept}>
          <label className="checkbox">
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
            {t("consent.agree")}
          </label>
          <button type="submit" disabled={!agreed}>
            {t("consent.submit")}
          </button>
        </form>
      )}
      {error !== null && <ErrorText error={error} />}
    </section>
  );
}
