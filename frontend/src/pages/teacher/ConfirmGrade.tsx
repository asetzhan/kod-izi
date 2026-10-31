import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiSend } from "../../api/client";
import type { AiGrade, CriterionCode, Observation, TeacherGrade } from "../../api/types";
import { useResource } from "../../api/useResource";
import { ErrorText } from "../../components/Status";

const CODES: CriterionCode[] = [
  "understanding",
  "algorithm",
  "correctness",
  "code_quality",
  "debugging",
  "explanation",
];
type Level = "low" | "mid" | "high";

/** ФТ-03: confirm or correct the AI grade; the reason is required for a correction. */
export function ConfirmGrade({ submissionId, ai }: { submissionId: number; ai: AiGrade | undefined }) {
  const { t } = useTranslation();
  const current = useResource<TeacherGrade | null>(`/api/submissions/${submissionId}/teacher-grade`);
  const aiLevels = Object.fromEntries((ai?.criteria ?? []).map((c) => [c.code, c.level])) as Record<string, Level>;
  const [levels, setLevels] = useState<Record<string, Level>>(
    Object.fromEntries(CODES.map((c) => [c, aiLevels[c] ?? "mid"])),
  );
  const [components, setComponents] = useState({
    F: ai?.components.F ?? 0,
    E: ai?.components.E ?? 0,
    A: ai?.components.A ?? 0,
  });
  const [feedback, setFeedback] = useState(ai?.feedback ?? "");
  const [nextStep, setNextStep] = useState(ai?.next_step ?? "");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const changed = CODES.some((c) => aiLevels[c] !== undefined && aiLevels[c] !== levels[c]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await apiSend("POST", `/api/submissions/${submissionId}/teacher-grade`, {
        levels,
        components,
        feedback,
        next_step: nextStep,
        reason,
      });
      current.reload();
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <section className="card">
      <h2>{t("confirm.title")}</h2>
      {current.data && (
        <p role="status">
          {t("confirm.confirmed", { score: current.data.score })}
          {current.data.agrees_with_ai ? ` · ${t("confirm.agrees")}` : ` · ${t("confirm.corrected")}`}
        </p>
      )}
      <form className="inline-form" onSubmit={submit}>
        {CODES.map((code) => (
          <label key={code}>
            {t(`review.criteria.${code}`)}
            <select
              value={levels[code]}
              onChange={(e) => setLevels({ ...levels, [code]: e.target.value as Level })}
            >
              {(["low", "mid", "high"] as const).map((lv) => (
                <option key={lv} value={lv}>
                  {t(`review.levels.${lv}`)}
                  {aiLevels[code] === lv ? ` (${t("confirm.aiSaid")})` : ""}
                </option>
              ))}
            </select>
          </label>
        ))}
        <div className="row">
          {(["F", "E", "A"] as const).map((k) => (
            <label key={k}>
              {k}
              <input
                type="number"
                min={0}
                max={100}
                value={components[k]}
                onChange={(e) => setComponents({ ...components, [k]: Number(e.target.value) })}
              />
            </label>
          ))}
        </div>
        <label>
          {t("confirm.feedback")}
          <textarea required rows={4} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
        </label>
        <label>
          {t("confirm.nextStep")}
          <input value={nextStep} onChange={(e) => setNextStep(e.target.value)} />
        </label>
        <label>
          {t("confirm.reason")}
          <textarea required={changed} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <button type="submit">{t("confirm.submit")}</button>
        {error !== null && <ErrorText error={error} />}
      </form>
    </section>
  );
}

/** ФТ-36: the teacher's own observations and comments on signals. */
export function Observations({ submissionId }: { submissionId: number }) {
  const { t } = useTranslation();
  const list = useResource<Observation[]>(`/api/submissions/${submissionId}/observations`);
  const [kind, setKind] = useState<Observation["kind"]>("oral_defense");
  const [text, setText] = useState("");
  const [error, setError] = useState<unknown>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await apiSend("POST", `/api/submissions/${submissionId}/observations`, { kind, text });
      setText("");
      list.reload();
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <section className="card">
      <h2>{t("observations.title")}</h2>
      <ul>
        {list.data?.map((o) => (
          <li key={o.id}>
            <strong>{t(`observations.kinds.${o.kind}`)}:</strong> {o.text}
          </li>
        ))}
      </ul>
      <form className="inline-form" onSubmit={submit}>
        <label>
          {t("observations.kind")}
          <select value={kind} onChange={(e) => setKind(e.target.value as Observation["kind"])}>
            {(["oral_defense", "signal_comment", "note"] as const).map((k) => (
              <option key={k} value={k}>
                {t(`observations.kinds.${k}`)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("observations.text")}
          <textarea required rows={2} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        <button type="submit">{t("observations.add")}</button>
        {error !== null && <ErrorText error={error} />}
      </form>
    </section>
  );
}
