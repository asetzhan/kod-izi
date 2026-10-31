import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiSend } from "../../api/client";
import type { AssistantMessage, GenAiMode } from "../../api/types";
import { useResource } from "../../api/useResource";
import { ErrorText } from "../../components/Status";

/** ФТ-47: the AI assistant, shown only when the assessment allows it. */
export function AssistantPanel({
  sessionId,
  mode,
  code,
  disabled,
}: {
  sessionId: string;
  mode: GenAiMode;
  code: string;
  disabled: boolean;
}) {
  const { t, i18n } = useTranslation();
  const history = useResource<AssistantMessage[]>(`/api/sessions/${sessionId}/assistant`);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (mode === "forbidden") return null;

  const ask = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiSend("POST", `/api/sessions/${sessionId}/assistant`, {
        question,
        code,
        ui_language: i18n.language === "ru" ? "ru" : "kk",
      });
      setQuestion("");
      history.reload();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card" aria-label={t("assistant.title")}>
      <h2>{t("assistant.title")}</h2>
      <p className="muted">{t(`assistant.mode.${mode}`)}</p>
      <ul className="assistant">
        {history.data?.map((m) => (
          <li key={m.id}>
            <p>
              <strong>{t("assistant.you")}:</strong> {m.question}
            </p>
            <p className={m.blocked ? "muted" : undefined}>
              <strong>AI ({t("assistant.preliminary")}):</strong> <span className="statement">{m.answer}</span>
            </p>
          </li>
        ))}
      </ul>
      <form className="inline-form" onSubmit={ask}>
        <label>
          {t("assistant.question")}
          <textarea required rows={2} maxLength={4000} value={question} onChange={(e) => setQuestion(e.target.value)} />
        </label>
        <button type="submit" disabled={disabled || busy}>
          {t("assistant.ask")}
        </button>
      </form>
      {error !== null && <ErrorText error={error} />}
    </section>
  );
}
