import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import { apiSend } from "../../api/client";
import type { Contest, ContestDetail, Standings } from "../../api/olympiad";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";

function when(contest: Contest): string {
  return `${new Date(contest.starts_at).toLocaleString()} — ${new Date(contest.ends_at).toLocaleString()}`;
}

/** ОТ-02, ОТ-03: contests of the student's courses; a finished one can be written virtually. */
export function ContestsPage() {
  const { t } = useTranslation();
  const contests = useResource<Contest[]>("/api/contests");
  const [error, setError] = useState<unknown>(null);

  const startVirtual = async (id: number) => {
    setError(null);
    try {
      await apiSend("POST", `/api/contests/${id}/virtual`);
      contests.reload();
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <section className="card">
      <h1>{t("contest.list")}</h1>
      <Status loading={contests.loading} error={contests.error} />
      {contests.data?.length === 0 && <p className="muted">{t("contest.none")}</p>}
      <ul>
        {contests.data?.map((c) => (
          <li key={c.id}>
            {c.state === "upcoming" ? c.title : <Link to={`/student/contests/${c.id}`}>{c.title}</Link>} (
            {c.format.toUpperCase()}, {t(`contest.state.${c.state}`)}): {when(c)}
            {c.state === "finished" && !c.my_virtual && (
              <>
                {" "}
                <button type="button" onClick={() => startVirtual(c.id)}>
                  {t("contest.startVirtual")}
                </button>
              </>
            )}
            {c.my_virtual && (
              <span className="muted">
                {" "}
                {t("contest.virtualUntil", { time: new Date(c.my_virtual.ends_at).toLocaleString() })}
              </span>
            )}
          </li>
        ))}
      </ul>
      {error !== null && <ErrorText error={error} />}
    </section>
  );
}

/** A contest: problems (from the start; after the end for upsolving) and the standings. */
export function ContestPage({ base = "/student" }: { base?: string }) {
  const { contestId } = useParams();
  const { t } = useTranslation();
  const contest = useResource<ContestDetail>(`/api/contests/${contestId}`);

  if (!contest.data) return <Status loading={contest.loading} error={contest.error} />;
  const c = contest.data;
  return (
    <>
      <section className="card">
        <h1>{c.title}</h1>
        <p className="muted">
          {c.format.toUpperCase()} · {when(c)}
        </p>
        <p className="muted">{c.writing ? t("contest.writing") : t("contest.notWriting")}</p>
        <p className="muted">{t("contest.noAi")}</p>
        <ol type="A">
          {c.problems.map((p) => (
            <li key={p.id}>
              {base === "/student" ? (
                <Link to={`/student/contests/${c.id}/tasks/${p.id}`}>{p.title}</Link>
              ) : (
                p.title
              )}{" "}
              <span className="muted">
                {t("workspace.limits", { time: p.time_limit_ms, memory: Math.round(p.memory_limit_kb / 1024) })}
              </span>
            </li>
          ))}
        </ol>
      </section>
      <StandingsTable contestId={c.id} />
    </>
  );
}

export function StandingsTable({ contestId }: { contestId: number }) {
  const { t } = useTranslation();
  const standings = useResource<Standings>(`/api/contests/${contestId}/standings`);

  if (!standings.data) return <Status loading={standings.loading} error={standings.error} />;
  const s = standings.data;
  const icpc = s.format === "icpc";
  return (
    <section className="card">
      <h2>{t("contest.standings")}</h2>
      {s.frozen && <p role="status">{t("contest.frozen")}</p>}
      <button type="button" onClick={standings.reload}>
        {t("contest.refresh")}
      </button>
      <table aria-label={t("contest.standings")}>
        <thead>
          <tr>
            <th>#</th>
            <th>{t("contest.participant")}</th>
            {s.tasks.map((task) => (
              <th key={task.id}>{task.label}</th>
            ))}
            <th>{icpc ? t("contest.solved") : t("contest.score")}</th>
            {icpc && <th>{t("contest.penalty")}</th>}
          </tr>
        </thead>
        <tbody>
          {s.rows.map((row, i) => (
            <tr key={i} className={row.me ? "me" : undefined}>
              <td>{row.rank}</td>
              <td>
                {row.me ? t("contest.me") : (row.name ?? t("contest.anonymous", { n: row.rank }))}
                {row.virtual && ` (${t("contest.virtual")})`}
              </td>
              {row.cells.map((cell, j) => (
                <td key={j}>
                  {icpc
                    ? cell.solved
                      ? `+${cell.wrong || ""} ${cell.minute}′`
                      : cell.pending
                        ? `? ${cell.wrong ? `−${cell.wrong}` : ""}`
                        : cell.wrong
                          ? `−${cell.wrong}`
                          : ""
                    : cell.pending
                      ? `${cell.score} ?`
                      : cell.tried
                        ? cell.score
                        : ""}
                </td>
              ))}
              <td>{icpc ? row.solved : row.score}</td>
              {icpc && <td>{row.penalty}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
