import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { apiSend } from "../api/client";
import { useResource } from "../api/useResource";
import { ErrorText, Status } from "../components/Status";

interface Component {
  kc_id: number;
  code: string;
  name: string;
  topic_code: string;
  attempts: number;
  p_learned: number;
  mastered: boolean;
}

interface Progress {
  next: {
    weakest_criterion: string | null;
    weak_components: { kc_id: number; name: string; topic_code: string; p_learned: number }[];
    target_level: string | null;
    tasks: { id: number; title: string; level: string | null }[];
    lessons: { title: string; url: string }[];
  };
  trajectory: {
    course: string;
    results: {
      at: string;
      task: string;
      level: string | null;
      assessment: string | null;
      score: number;
      criteria: Record<string, string>;
    }[];
    components: Component[];
    mastered_components: number;
  };
}

const percent = (p: number) => `${Math.round(p * 100)}%`;

/** ФТ-39 student model, ФТ-44 next step, ФТ-45 trajectory. */
function ProgressView({
  data,
  onAssign,
}: {
  data: Progress;
  onAssign?: (taskId: number) => Promise<void>;
}) {
  const { t } = useTranslation();
  const { next, trajectory } = data;
  return (
    <>
      <section className="card">
        <h2>{t("progress.next")}</h2>
        {next.weakest_criterion && (
          <p>{t("progress.weakestCriterion", { criterion: t(`review.criteria.${next.weakest_criterion}`) })}</p>
        )}
        {next.weak_components.length > 0 ? (
          <p>
            {t("progress.weakComponents")}:{" "}
            {next.weak_components.map((c) => `${c.name} (${c.topic_code}, ${percent(c.p_learned)})`).join("; ")}
          </p>
        ) : (
          <p>{t("progress.allMastered")}</p>
        )}
        {next.target_level && <p>{t("progress.targetLevel", { level: next.target_level })}</p>}
        {next.lessons.length > 0 && (
          <p>
            {t("progress.lessons")}:{" "}
            {next.lessons.map((lesson, i) => (
              <span key={lesson.url}>
                {i > 0 && ", "}
                <a href={lesson.url} target="_blank" rel="noreferrer">
                  {lesson.title}
                </a>
              </span>
            ))}
          </p>
        )}
        {onAssign && (
          <ul aria-label={t("progress.suggestedTasks")}>
            {next.tasks.map((task) => (
              <li key={task.id}>
                {task.title} {task.level && `(${task.level})`}{" "}
                <button type="button" onClick={() => void onAssign(task.id)}>
                  {t("assignments.assign")}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card">
        <h2>{t("progress.model")}</h2>
        <p className="muted">
          {t("progress.mastered", {
            n: trajectory.mastered_components,
            total: trajectory.components.length,
          })}
        </p>
        <table aria-label={t("progress.model")}>
          <thead>
            <tr>
              <th>{t("progress.component")}</th>
              <th>{t("progress.attempts")}</th>
              <th>{t("progress.probability")}</th>
            </tr>
          </thead>
          <tbody>
            {trajectory.components.map((c) => (
              <tr key={c.kc_id} className={c.mastered ? "ok" : undefined}>
                <td>
                  {c.topic_code} · {c.name}
                </td>
                <td>{c.attempts}</td>
                <td>
                  <meter min={0} max={1} value={c.p_learned} aria-label={c.name} /> {percent(c.p_learned)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="card">
        <h2>{t("progress.trajectory")}</h2>
        {trajectory.results.length === 0 && <p className="muted">{t("progress.noResults")}</p>}
        <ol>
          {trajectory.results.map((r) => (
            <li key={`${r.at}-${r.task}`}>
              {new Date(r.at).toLocaleDateString()} · {r.assessment ?? t("progress.individual")} · {r.task}{" "}
              {r.level && `(${r.level})`}: <strong>{Math.round(r.score)}</strong>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}

/** The teacher's view of one student, with one-click assignment of a suggested task (ФТ-05). */
export function StudentProgressPage() {
  const { courseId, studentId } = useParams();
  const { t } = useTranslation();
  const data = useResource<Progress>(`/api/courses/${courseId}/students/${studentId}/progress`);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const assign = async (taskId: number) => {
    setError(null);
    try {
      await apiSend("POST", `/api/courses/${courseId}/assignments`, {
        task_id: taskId,
        user_id: Number(studentId),
      });
      setMessage(t("progress.assigned"));
    } catch (caught) {
      setError(caught);
    }
  };

  if (!data.data) return <Status loading={data.loading} error={data.error} />;
  return (
    <>
      <section className="card">
        <h1>{t("progress.studentTitle")}</h1>
        {message && <p role="status">{message}</p>}
        {error !== null && <ErrorText error={error} />}
      </section>
      <ProgressView data={data.data} onAssign={assign} />
    </>
  );
}

/** The student's own progress in a course. */
export function MyProgressPage() {
  const { courseId } = useParams();
  const { t } = useTranslation();
  const data = useResource<Progress>(`/api/my/progress?course_id=${courseId}`);
  if (!data.data) return <Status loading={data.loading} error={data.error} />;
  return (
    <>
      <section className="card">
        <h1>{t("progress.myTitle", { course: data.data.trajectory.course })}</h1>
      </section>
      <ProgressView data={data.data} />
    </>
  );
}
