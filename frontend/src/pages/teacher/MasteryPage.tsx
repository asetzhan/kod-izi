import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import type { Course, MasteryRow } from "../../api/types";
import { useResource } from "../../api/useResource";
import { Status } from "../../components/Status";

interface StudentMastery {
  user_id: number;
  full_name: string;
  rows: MasteryRow[];
}

/** ФТ-43: Bespalko coefficient K = a / p per student, topic and level (spec 5.3). */
export function MasteryPage() {
  const { courseId } = useParams();
  const { t } = useTranslation();
  const data = useResource<StudentMastery[]>(`/api/courses/${courseId}/mastery`);
  const course = useResource<Course>(`/api/courses/${courseId}`);
  const topics = new Map((course.data?.topics ?? []).map((tp) => [tp.id, `${tp.code} ${tp.title}`]));

  return (
    <section className="card">
      <h1>{t("masteryPage.title")}</h1>
      <p className="muted">{t("masteryPage.hint")}</p>
      <Status loading={data.loading} error={data.error} />
      <table>
        <thead>
          <tr>
            <th>{t("activity.student")}</th>
            <th>{t("task.topic")}</th>
            <th>{t("task.level")}</th>
            <th>a / p</th>
            <th>K</th>
          </tr>
        </thead>
        <tbody>
          {data.data?.flatMap((s) =>
            s.rows.map((row, i) => (
              <tr key={`${s.user_id}-${i}`} className={row.mastered ? "mastered" : undefined}>
                <td>{i === 0 ? s.full_name : ""}</td>
                <td>{row.topic_id ? topics.get(row.topic_id) : "—"}</td>
                <td>{row.level ?? "—"}</td>
                <td>
                  {row.a} / {row.p}
                </td>
                <td>
                  {row.k ?? "—"} {row.mastered ? "✓" : ""}
                </td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </section>
  );
}
