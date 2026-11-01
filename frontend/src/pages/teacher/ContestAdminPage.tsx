import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { apiSend } from "../../api/client";
import type { Contest, ContestFormat } from "../../api/olympiad";
import type { TaskSummary } from "../../api/types";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";
import { StandingsTable } from "../student/ContestPages";

function isoFromLocal(value: string): string {
  return new Date(value).toISOString();
}

/** ОТ-02: the course's contests; a coach or teacher creates one from approved problems. */
export function ContestAdminPage() {
  const { courseId } = useParams();
  const { t } = useTranslation();
  const contests = useResource<Contest[]>(`/api/contests?course_id=${courseId}`);
  const tasks = useResource<TaskSummary[]>(`/api/tasks?course_id=${courseId}&status=approved`);
  const [title, setTitle] = useState("");
  const [format, setFormat] = useState<ContestFormat>("icpc");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [freeze, setFreeze] = useState(60);
  const [penalty, setPenalty] = useState(20);
  const [chosen, setChosen] = useState<number[]>([]);
  const [shown, setShown] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await apiSend("POST", `/api/courses/${courseId}/contests`, {
        title,
        format,
        starts_at: isoFromLocal(startsAt),
        ends_at: isoFromLocal(endsAt),
        freeze_minutes: freeze,
        penalty_minutes: penalty,
        task_ids: chosen,
      });
      setTitle("");
      setChosen([]);
      contests.reload();
    } catch (caught) {
      setError(caught);
    }
  };

  const toggle = (id: number) =>
    setChosen(chosen.includes(id) ? chosen.filter((x) => x !== id) : [...chosen, id]);

  return (
    <>
      <section className="card">
        <h1>{t("contest.list")}</h1>
        <Status loading={contests.loading} error={contests.error} />
        {contests.data?.length === 0 && <p className="muted">{t("contest.none")}</p>}
        <ul>
          {contests.data?.map((c) => (
            <li key={c.id}>
              {c.title} ({c.format.toUpperCase()}, {t(`contest.state.${c.state}`)}):{" "}
              {new Date(c.starts_at).toLocaleString()} — {new Date(c.ends_at).toLocaleString()}{" "}
              {c.state !== "upcoming" && (
                <button type="button" className="link" onClick={() => setShown(c.id)}>
                  {t("contest.standings")}
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>
      {shown !== null && <StandingsTable key={shown} contestId={shown} />}
      <section className="card">
        <h2>{t("contest.create")}</h2>
        <form className="inline-form" onSubmit={create}>
          <label>
            {t("contest.title")}
            <input required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label>
            {t("contest.format")}
            <select value={format} onChange={(e) => setFormat(e.target.value as ContestFormat)}>
              <option value="icpc">ICPC</option>
              <option value="ioi">IOI</option>
            </select>
          </label>
          <label>
            {t("contest.startsAt")}
            <input type="datetime-local" required value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />
          </label>
          <label>
            {t("contest.endsAt")}
            <input type="datetime-local" required value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
          </label>
          <label>
            {t("contest.freezeMinutes")}
            <input type="number" min={0} max={600} value={freeze} onChange={(e) => setFreeze(Number(e.target.value))} />
          </label>
          {format === "icpc" && (
            <label>
              {t("contest.penaltyMinutes")}
              <input
                type="number"
                min={0}
                max={120}
                value={penalty}
                onChange={(e) => setPenalty(Number(e.target.value))}
              />
            </label>
          )}
          <fieldset>
            <legend>{t("contest.problems")}</legend>
            <Status loading={tasks.loading} error={tasks.error} />
            {tasks.data?.length === 0 && <p className="muted">{t("contest.noApproved")}</p>}
            {tasks.data?.map((task) => (
              <label key={task.id} className="checkbox">
                <input type="checkbox" checked={chosen.includes(task.id)} onChange={() => toggle(task.id)} />
                {task.title} {task.level && `(${task.level})`}
              </label>
            ))}
          </fieldset>
          <button type="submit" disabled={chosen.length === 0}>
            {t("contest.create")}
          </button>
        </form>
        {error !== null && <ErrorText error={error} />}
      </section>
    </>
  );
}
