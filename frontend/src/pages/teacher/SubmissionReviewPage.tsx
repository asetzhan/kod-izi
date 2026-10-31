import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { apiGet, apiSend } from "../../api/client";
import type { AiGrade, ChunkView, SubmissionResult } from "../../api/types";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";
import { ConfirmGrade, Observations } from "./ConfirmGrade";

/**
 * A submission for the teacher: tests and the preliminary AI grade with its evidence
 * (ФТ-34, ФТ-35, ФТ-48). Confirming or correcting the grade is stage 4.
 */
export function SubmissionReviewPage() {
  const { submissionId } = useParams();
  const { t } = useTranslation();
  const submission = useResource<SubmissionResult>(`/api/submissions/${submissionId}`);
  const grades = useResource<AiGrade[]>(`/api/submissions/${submissionId}/ai-grades`);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const regrade = async () => {
    setBusy(true);
    setError(null);
    try {
      await apiSend("POST", `/api/submissions/${submissionId}/ai-grades`);
      grades.reload();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };

  if (!submission.data) return <Status loading={submission.loading} error={submission.error} />;
  const s = submission.data;
  const latest = grades.data?.[0];

  return (
    <>
      <section className="card">
        <h1>{t("review.title", { id: s.id })}</h1>
        <p>
          {s.verdict ? t(`verdicts.${s.verdict}`) : t(`submissionStatus.${s.status}`)} ·{" "}
          {t("workspace.passed", { passed: s.tests_passed, total: s.tests_total })}
        </p>
        {s.explanation && (
          <>
            <h3>{t("review.explanation")}</h3>
            <p className="statement">{s.explanation}</p>
            <ul>
              {s.questions.map((q, i) => (
                <li key={i}>
                  <strong>{q.question}</strong> — {q.answer ?? "—"}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      <section className="card">
        <h2>{t("review.aiGrade")}</h2>
        <p className="muted">{t("review.preliminary")}</p>
        <Status loading={grades.loading} error={grades.error} />
        {latest ? <GradeView grade={latest} /> : !grades.loading && <p>{t("review.noGrade")}</p>}
        <button type="button" disabled={busy} onClick={regrade}>
          {t("review.regrade")}
        </button>
        {error !== null && <ErrorText error={error} />}
      </section>
      {!grades.loading && <ConfirmGrade key={latest?.id ?? "none"} submissionId={s.id} ai={latest} />}
      <Observations submissionId={s.id} />
    </>
  );
}

function GradeView({ grade }: { grade: AiGrade }) {
  const { t } = useTranslation();
  const [fragment, setFragment] = useState<ChunkView | null>(null);

  // The grade cites fragments by reference; find the cited one among those it used.
  const openFragment = async (ref: string) => {
    const chunks = await Promise.all(grade.fragment_ids.map((id) => apiGet<ChunkView>(`/api/chunks/${id}`)));
    const refOf = (c: ChunkView) =>
      `${c.material_title}${c.chapter ? `, ${c.chapter}` : ""}${c.page !== null ? `, ${c.page}-бет` : ""}`;
    setFragment(chunks.find((c) => refOf(c) === ref) ?? chunks[0] ?? null);
  };

  return (
    <div>
      <p>
        {t(`review.status.${grade.status}`)}
        {grade.score !== null && (
          <>
            {" · "}S = <strong>{grade.score}</strong> (F {grade.components.F}, E {grade.components.E}, A{" "}
            {grade.components.A})
          </>
        )}
      </p>
      {grade.review_reasons.length > 0 && (
        <ul className="flag">
          {grade.review_reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      {grade.flags.length > 0 && (
        <p>
          {t("review.flags")}: {grade.flags.map((f) => t(`review.flagNames.${f}`, f)).join(", ")}
        </p>
      )}
      <table>
        <thead>
          <tr>
            <th>{t("review.criterion")}</th>
            <th>{t("review.level")}</th>
            <th>{t("review.evidence")}</th>
          </tr>
        </thead>
        <tbody>
          {grade.criteria.map((c) => (
            <tr key={c.code}>
              <td>{t(`review.criteria.${c.code}`)}</td>
              <td>{t(`review.levels.${c.level}`)}</td>
              <td>
                <ul>
                  {c.evidence.map((e, i) => (
                    <li key={i}>
                      {e.type === "book" ? (
                        <button type="button" className="link" onClick={() => openFragment(e.ref)}>
                          {e.ref}
                        </button>
                      ) : (
                        <span>{e.ref}</span>
                      )}
                      {e.quote && <q> {e.quote}</q>}
                    </li>
                  ))}
                </ul>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {grade.feedback && (
        <>
          <h3>{t("review.feedback")}</h3>
          <p className="statement">{grade.feedback}</p>
        </>
      )}
      {fragment && (
        <aside className="card" aria-label={t("review.fragment")}>
          <strong>
            {fragment.material_title}, v{fragment.version}
            {fragment.chapter && `, ${fragment.chapter}`}
            {fragment.page !== null && `, ${fragment.page}-бет`}
          </strong>
          <p className="statement">{fragment.text}</p>
        </aside>
      )}
      <p className="muted">
        {grade.model} · {grade.prompt_version}
      </p>
    </div>
  );
}
