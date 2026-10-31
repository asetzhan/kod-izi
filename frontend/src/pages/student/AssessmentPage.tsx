import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import type { StudentAssessment } from "../../api/types";
import { useResource } from "../../api/useResource";
import { Status } from "../../components/Status";

/** A started assessment: its tasks (ФТ-02, ФТ-24). */
export function AssessmentPage() {
  const { assessmentId } = useParams();
  const { t } = useTranslation();
  const assessment = useResource<StudentAssessment>(`/api/assessments/${assessmentId}`);
  if (!assessment.data) return <Status loading={assessment.loading} error={assessment.error} />;
  const a = assessment.data;
  return (
    <section className="card">
      <h1>{a.title}</h1>
      <p className="muted">
        {new Date(a.starts_at).toLocaleString()} — {new Date(a.ends_at).toLocaleString()} ·{" "}
        {t("assessment.genaiMode")}: {t(`genai.${a.genai_mode}`)}
      </p>
      <ol>
        {a.tasks.map((task) => (
          <li key={task.id}>
            <Link to={`/student/assessments/${a.id}/tasks/${task.id}`}>{task.title}</Link>
            {task.level && <small> ({t("task.level")} {task.level})</small>}
          </li>
        ))}
      </ol>
    </section>
  );
}
