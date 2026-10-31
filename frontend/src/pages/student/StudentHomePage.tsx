import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { Assessment, Course, CourseSummary } from "../../api/types";
import { useResource } from "../../api/useResource";
import { Status } from "../../components/Status";
import { TopicList } from "../../components/TopicList";

/** Student cabinet: own courses with Stepik lessons (ФТ-12) and the assessment schedule. */
export function StudentHomePage() {
  const { t } = useTranslation();
  const courses = useResource<CourseSummary[]>("/api/courses");
  const assessments = useResource<Assessment[]>("/api/assessments");

  return (
    <>
      <section className="card">
        <h1>{t("cabinet.student")}</h1>
        <h2>{t("assessment.schedule")}</h2>
        <Status loading={assessments.loading} error={assessments.error} />
        {assessments.data?.length === 0 && <p className="muted">{t("assessment.none")}</p>}
        <ul>
          {assessments.data?.map((a) => (
            <li key={a.id}>
              {new Date(a.starts_at) <= new Date() ? (
                <Link to={`/student/assessments/${a.id}`}>{a.title}</Link>
              ) : (
                a.title
              )}
              : {new Date(a.starts_at).toLocaleString()} —{" "}
              {new Date(a.ends_at).toLocaleString()} ({t(`genai.${a.genai_mode}`)})
            </li>
          ))}
        </ul>
      </section>
      <Status loading={courses.loading} error={courses.error} />
      {courses.data?.length === 0 && <p className="card muted">{t("course.noCourses")}</p>}
      {courses.data?.map((c) => <StudentCourse key={c.id} id={c.id} />)}
    </>
  );
}

function StudentCourse({ id }: { id: number }) {
  const course = useResource<Course>(`/api/courses/${id}`);
  if (!course.data) return <Status loading={course.loading} error={course.error} />;
  return (
    <section className="card">
      <h2>{course.data.title}</h2>
      <TopicList topics={course.data.topics} />
    </section>
  );
}
