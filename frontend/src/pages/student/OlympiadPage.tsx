import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { OlympiadOverview, ProblemSummary, Recommendations } from "../../api/olympiad";
import { useResource } from "../../api/useResource";
import { Status } from "../../components/Status";

/** Part 2 (spec 4): reference by module (ОТ-10), recommendations (ОТ-04), problem bank (ОТ-01). */
export function OlympiadPage() {
  const { t } = useTranslation();
  const overview = useResource<OlympiadOverview>("/api/olympiad");

  if (!overview.data) return <Status loading={overview.loading} error={overview.error} />;
  const { unlock, courses, practice } = overview.data;

  return (
    <>
      <section className="card">
        <h1>{t("olympiad.title")}</h1>
        <p>
          <Link to="/student/contests">{t("contest.list")}</Link>
        </p>
        {!unlock.unlocked && (
          <p role="alert">{t("olympiad.locked", { topics: unlock.missing.join(", ") })}</p>
        )}
      </section>
      {unlock.unlocked && <RecommendedProblems />}
      {unlock.unlocked && <ProblemBank />}
      {courses.map((course) => (
        <section key={course.id} className="card">
          <h2>
            {course.url ? (
              <a href={course.url} target="_blank" rel="noreferrer">
                {course.title}
              </a>
            ) : (
              course.title
            )}
          </h2>
          {course.topics.map((topic) => (
            <div key={topic.id}>
              <h3>
                {topic.code} {topic.title}
              </h3>
              <ul>
                {topic.lessons.map((lesson) => (
                  <li key={lesson.url}>
                    <a href={lesson.url} target="_blank" rel="noreferrer">
                      {lesson.title}
                    </a>
                  </li>
                ))}
              </ul>
              {topic.resources.length > 0 && (
                <p className="muted">
                  {t("olympiad.extra")}:{" "}
                  {topic.resources.map((r, i) => (
                    <span key={r.url}>
                      {i > 0 && ", "}
                      <a href={r.url} target="_blank" rel="noreferrer" title={r.purpose}>
                        {r.name}
                      </a>
                    </span>
                  ))}
                </p>
              )}
            </div>
          ))}
        </section>
      ))}
      <section className="card">
        <h2>{t("olympiad.practice")}</h2>
        <ul>
          {practice.rules.map((rule) => (
            <li key={rule}>{rule}</li>
          ))}
        </ul>
        <ul>
          {practice.resources.map((r) => (
            <li key={r.url}>
              <a href={r.url} target="_blank" rel="noreferrer">
                {r.name}
              </a>{" "}
              — {r.purpose}
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

function ProblemRow({ p }: { p: ProblemSummary }) {
  const { t } = useTranslation();
  return (
    <tr>
      <td>
        <Link to={`/student/olympiad/problems/${p.id}`}>{p.title}</Link>
      </td>
      <td>{p.level ?? "—"}</td>
      <td>{p.cf_rating ?? "—"}</td>
      <td>{p.tags.join(", ")}</td>
      <td>{Math.round(p.memory_limit_kb / 1024)} MB</td>
      <td>{p.solved ? t("olympiad.solved") : ""}</td>
    </tr>
  );
}

function ProblemTable({ problems }: { problems: ProblemSummary[] }) {
  const { t } = useTranslation();
  return (
    <table>
      <thead>
        <tr>
          <th>{t("olympiad.problem")}</th>
          <th>{t("task.level")}</th>
          <th>{t("olympiad.rating")}</th>
          <th>{t("olympiad.tags")}</th>
          <th>{t("olympiad.memory")}</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {problems.map((p) => (
          <ProblemRow key={p.id} p={p} />
        ))}
      </tbody>
    </table>
  );
}

function RecommendedProblems() {
  const { t } = useTranslation();
  const data = useResource<Recommendations>("/api/olympiad/recommendations");
  if (!data.data) return <Status loading={data.loading} error={data.error} />;
  return (
    <section className="card">
      <h2>{t("olympiad.recommended")}</h2>
      <p className="muted">
        {t("olympiad.myRating", { rating: data.data.rating, low: data.data.range[0], high: data.data.range[1] })}
      </p>
      {data.data.problems.length === 0 ? (
        <p className="muted">{t("olympiad.noRecommendations")}</p>
      ) : (
        <ProblemTable problems={data.data.problems} />
      )}
    </section>
  );
}

function ProblemBank() {
  const { t } = useTranslation();
  const [tag, setTag] = useState("");
  const [minRating, setMinRating] = useState("");
  const [maxRating, setMaxRating] = useState("");
  const query = new URLSearchParams();
  if (tag) query.set("tag", tag);
  if (minRating) query.set("min_rating", minRating);
  if (maxRating) query.set("max_rating", maxRating);
  const problems = useResource<ProblemSummary[]>(
    `/api/olympiad/problems${query.size ? `?${query.toString()}` : ""}`,
  );

  return (
    <section className="card">
      <h2>{t("olympiad.bank")}</h2>
      <div className="row">
        <label>
          {t("olympiad.tags")}
          <input value={tag} onChange={(e) => setTag(e.target.value)} />
        </label>
        <label>
          {t("olympiad.minRating")}
          <input type="number" value={minRating} onChange={(e) => setMinRating(e.target.value)} />
        </label>
        <label>
          {t("olympiad.maxRating")}
          <input type="number" value={maxRating} onChange={(e) => setMaxRating(e.target.value)} />
        </label>
      </div>
      <Status loading={problems.loading} error={problems.error} />
      {problems.data && <ProblemTable problems={problems.data} />}
    </section>
  );
}
