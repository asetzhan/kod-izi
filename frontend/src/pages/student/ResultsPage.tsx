import { useTranslation } from "react-i18next";

import type { CourseSummary, MasteryRow, StudentResult } from "../../api/types";
import { useResource } from "../../api/useResource";
import { Status } from "../../components/Status";

/**
 * ФТ-41, ФТ-42: results the teacher has confirmed, with book references. Text written
 * by AI is marked «AI» and «алдын ала». ФТ-43: mastery of each topic and level.
 */
export function ResultsPage() {
  const { t } = useTranslation();
  const results = useResource<StudentResult[]>("/api/my/results");
  const courses = useResource<CourseSummary[]>("/api/courses");

  return (
    <>
      <section className="card">
        <h1>{t("results.title")}</h1>
        <Status loading={results.loading} error={results.error} />
        {results.data?.length === 0 && <p className="muted">{t("results.none")}</p>}
        {results.data?.map((r) => (
          <article key={r.submission_id} className="result">
            <h2>{t("results.submission", { id: r.submission_id, score: r.score })}</h2>
            <table>
              <tbody>
                {r.criteria.map((c) => (
                  <tr key={c.code}>
                    <td>{c.name}</td>
                    <td>
                      <strong>{t(`review.levels.${c.level}`)}</strong>
                    </td>
                    <td>{c.interpretation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h3>
              {t("results.feedback")}{" "}
              {r.feedback_source !== "teacher" && (
                <span className="badge ai">{t(`results.source.${r.feedback_source}`)}</span>
              )}
            </h3>
            <p className="statement">{r.feedback}</p>
            {r.book_refs.length > 0 && (
              <p>
                {t("results.book")}: {r.book_refs.join("; ")}
              </p>
            )}
            {r.next_step && (
              <p>
                {t("results.nextStep")}: {r.next_step}
              </p>
            )}
          </article>
        ))}
      </section>
      {courses.data?.map((c) => <Mastery key={c.id} course={c} />)}
    </>
  );
}

function Mastery({ course }: { course: CourseSummary }) {
  const { t } = useTranslation();
  const rows = useResource<MasteryRow[]>(`/api/my/mastery?course_id=${course.id}`);
  if (!rows.data || rows.data.length === 0) return null;
  return (
    <section className="card">
      <h2>{t("results.mastery", { course: course.title })}</h2>
      <table>
        <thead>
          <tr>
            <th>{t("task.level")}</th>
            <th>a / p</th>
            <th>K</th>
            <th>{t("results.mastered")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.data.map((row, i) => (
            <tr key={i}>
              <td>{row.level ?? "—"}</td>
              <td>
                {row.a} / {row.p}
              </td>
              <td>{row.k ?? "—"}</td>
              <td>{row.mastered ? t("results.yes") : t("results.no")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
