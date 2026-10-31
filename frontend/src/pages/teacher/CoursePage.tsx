import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";

import { apiSend, apiUpload } from "../../api/client";
import type { Assessment, Course, GenAiMode, Task, TaskSummary } from "../../api/types";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";
import { TopicList } from "../../components/TopicList";

const GENAI_MODES: GenAiMode[] = ["forbidden", "hints_only", "open"];

/** Course: topics with Stepik links, task bank, import (ФТ-22), assessments (ФТ-02). */
export function CoursePage() {
  const { courseId } = useParams();
  const { t } = useTranslation();
  const course = useResource<Course>(`/api/courses/${courseId}`);
  const tasks = useResource<TaskSummary[]>(`/api/tasks?course_id=${courseId}`);
  const assessments = useResource<Assessment[]>(`/api/assessments?course_id=${courseId}`);

  if (!course.data) return <Status loading={course.loading} error={course.error} />;
  const topicTitle = new Map(course.data.topics.map((tp) => [tp.id, `${tp.code} ${tp.title}`]));

  return (
    <>
      <section className="card">
        <h1>{course.data.title}</h1>
        {course.data.source_url && (
          <p>
            <a href={course.data.source_url} target="_blank" rel="noopener noreferrer">
              {t("course.source")}
            </a>
          </p>
        )}
        <TopicList topics={course.data.topics} />
      </section>

      <section className="card">
        <h2>{t("task.bank")}</h2>
        {course.data.can_edit && (
          <p>
            <Link to={`/teacher/courses/${courseId}/tasks/new`}>{t("task.new")}</Link>
          </p>
        )}
        <Status loading={tasks.loading} error={tasks.error} />
        <table>
          <thead>
            <tr>
              <th>{t("task.title")}</th>
              <th>{t("task.topic")}</th>
              <th>{t("task.level")}</th>
              <th>{t("task.status")}</th>
            </tr>
          </thead>
          <tbody>
            {tasks.data?.map((task) => (
              <tr key={task.id}>
                <td>
                  <Link to={`/teacher/tasks/${task.id}`}>{task.title}</Link>
                </td>
                <td>{task.topic_id ? topicTitle.get(task.topic_id) : "—"}</td>
                <td>
                  {task.level ?? "—"} <small>({t(`levelStatus.${task.level_status}`)})</small>
                </td>
                <td>{t(`taskStatus.${task.status}`)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {course.data.can_edit && <ImportForm courseId={Number(courseId)} />}
      </section>

      <section className="card">
        <h2>{t("assessment.list")}</h2>
        <Status loading={assessments.loading} error={assessments.error} />
        <ul>
          {assessments.data?.map((a) => (
            <li key={a.id}>
              <Link to={`/teacher/assessments/${a.id}`}>{a.title}</Link>: {new Date(a.starts_at).toLocaleString()} —{" "}
              {new Date(a.ends_at).toLocaleString()}, {t(`genai.${a.genai_mode}`)},{" "}
              {t("assessment.taskCount", { count: a.task_ids.length })}
            </li>
          ))}
        </ul>
        {course.data.can_edit && (
          <AssessmentForm
            courseId={Number(courseId)}
            tasks={(tasks.data ?? []).filter((task) => task.status === "approved")}
            onCreated={assessments.reload}
          />
        )}
      </section>
    </>
  );
}

function ImportForm({ courseId }: { courseId: number }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<unknown>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    setError(null);
    try {
      const task = await apiUpload<Task>(`/api/courses/${courseId}/tasks/import`, file);
      navigate(`/teacher/tasks/${task.id}`);
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <form className="inline-form" onSubmit={submit}>
      <h3>{t("import.title")}</h3>
      <p className="muted">{t("import.hint")}</p>
      <label>
        {t("import.file")}
        <input
          type="file"
          accept=".zip,application/zip"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </label>
      <button type="submit" disabled={!file}>
        {t("import.submit")}
      </button>
      {error !== null && <ErrorText error={error} />}
    </form>
  );
}

function AssessmentForm({
  courseId,
  tasks,
  onCreated,
}: {
  courseId: number;
  tasks: TaskSummary[];
  onCreated: () => void;
}) {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [mode, setMode] = useState<GenAiMode>("forbidden");
  const [selected, setSelected] = useState<number[]>([]);
  const [error, setError] = useState<unknown>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await apiSend("POST", "/api/assessments", {
        course_id: courseId,
        title,
        starts_at: new Date(startsAt).toISOString(),
        ends_at: new Date(endsAt).toISOString(),
        genai_mode: mode,
        task_ids: selected,
      });
      setTitle("");
      setSelected([]);
      onCreated();
    } catch (caught) {
      setError(caught);
    }
  };

  const toggle = (id: number) =>
    setSelected((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));

  return (
    <form className="inline-form" onSubmit={submit}>
      <h3>{t("assessment.create")}</h3>
      <label>
        {t("assessment.title")}
        <input required value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        {t("assessment.startsAt")}
        <input type="datetime-local" required value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />
      </label>
      <label>
        {t("assessment.endsAt")}
        <input type="datetime-local" required value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
      </label>
      <label>
        {t("assessment.genaiMode")}
        <select value={mode} onChange={(e) => setMode(e.target.value as GenAiMode)}>
          {GENAI_MODES.map((m) => (
            <option key={m} value={m}>
              {t(`genai.${m}`)}
            </option>
          ))}
        </select>
      </label>
      <fieldset>
        <legend>{t("assessment.tasks")}</legend>
        {tasks.length === 0 && <p className="muted">{t("assessment.noApprovedTasks")}</p>}
        {tasks.map((task) => (
          <label key={task.id} className="checkbox">
            <input type="checkbox" checked={selected.includes(task.id)} onChange={() => toggle(task.id)} />
            {task.title} ({task.level})
          </label>
        ))}
      </fieldset>
      <button type="submit">{t("common.create")}</button>
      {error !== null && <ErrorText error={error} />}
    </form>
  );
}
