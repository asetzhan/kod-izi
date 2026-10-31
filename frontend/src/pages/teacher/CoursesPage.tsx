import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { apiSend } from "../../api/client";
import type { CoursePart, CourseSummary } from "../../api/types";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";

/** ФТ-01: the teacher's course list and a form to create a course. */
export function CoursesPage() {
  const { t } = useTranslation();
  const courses = useResource<CourseSummary[]>("/api/courses");
  const [title, setTitle] = useState("");
  const [part, setPart] = useState<CoursePart>("part1");
  const [error, setError] = useState<unknown>(null);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await apiSend("POST", "/api/courses", { title, part });
      setTitle("");
      courses.reload();
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <section className="card">
      <h1>{t("course.list")}</h1>
      <Status loading={courses.loading} error={courses.error} />
      <ul>
        {courses.data?.map((course) => (
          <li key={course.id}>
            <Link to={`/teacher/courses/${course.id}`}>{course.title}</Link>{" "}
            <small>({t(`course.parts.${course.part}`)})</small>
          </li>
        ))}
      </ul>
      <form className="inline-form" onSubmit={create}>
        <h2>{t("course.create")}</h2>
        <label>
          {t("course.title")}
          <input required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label>
          {t("course.part")}
          <select value={part} onChange={(e) => setPart(e.target.value as CoursePart)}>
            {(["part1", "part2", "other"] as const).map((p) => (
              <option key={p} value={p}>
                {t(`course.parts.${p}`)}
              </option>
            ))}
          </select>
        </label>
        <button type="submit">{t("common.create")}</button>
        {error !== null && <ErrorText error={error} />}
      </form>
    </section>
  );
}
