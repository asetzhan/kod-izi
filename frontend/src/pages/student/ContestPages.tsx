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
      {base === "/student" && c.state === "finished" && !c.writing && <ContestReview contestId={c.id} />}
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

interface Review {
  analyses: { id: number; task_id: number; title: string; editorial_md: string }[];
  took_part: boolean;
  upsolve: { task_id: number; label: string; title: string; solved_in_round: boolean; upsolved: boolean }[];
  explainable: { submission_id: number; task_id: number; explained: boolean }[];
}

/** ОТ-07: after the round: the analysis (AI, checked by the coach), upsolving, explanations. */
function ContestReview({ contestId }: { contestId: number }) {
  const { t } = useTranslation();
  const review = useResource<Review>(`/api/contests/${contestId}/review`);
  if (!review.data) return <Status loading={review.loading} error={review.error} />;
  const titles = new Map(review.data.upsolve.map((u) => [u.task_id, `${u.label}. ${u.title}`]));
  return (
    <section className="card">
      <h2>{t("review.contestTitle")}</h2>
      <h3>{t("review.upsolve")}</h3>
      <ul>
        {review.data.upsolve.map((u) => (
          <li key={u.task_id}>
            <Link to={`/student/olympiad/problems/${u.task_id}`}>
              {u.label}. {u.title}
            </Link>{" "}
            —{" "}
            {u.solved_in_round
              ? t("review.solvedInRound")
              : u.upsolved
                ? t("review.upsolved")
                : t("review.toUpsolve")}
          </li>
        ))}
      </ul>
      <h3>{t("review.analysis")}</h3>
      {!review.data.took_part ? (
        <p className="muted">{t("review.virtualFirst")}</p>
      ) : (
        review.data.analyses.length === 0 && <p className="muted">{t("review.noAnalysis")}</p>
      )}
      {review.data.analyses.map((a) => (
        <article key={a.id}>
          <h4>
            {a.title} <span className="badge">AI</span>
          </h4>
          <p className="statement">{a.editorial_md}</p>
        </article>
      ))}
      <h3>{t("review.explainTitle")}</h3>
      <p className="muted">{t("review.explainHelp")}</p>
      {review.data.explainable.map((e) => (
        <ExplainForm
          key={e.submission_id}
          submissionId={e.submission_id}
          title={titles.get(e.task_id) ?? `#${e.task_id}`}
          done={e.explained}
          onDone={review.reload}
        />
      ))}
    </section>
  );
}

function ExplainForm({
  submissionId,
  title,
  done,
  onDone,
}: {
  submissionId: number;
  title: string;
  done: boolean;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [error, setError] = useState<unknown>(null);
  if (done) return <p>{t("review.explained", { task: title })}</p>;
  const send = async () => {
    setError(null);
    try {
      await apiSend("POST", `/api/submissions/${submissionId}/explain`, { text });
      onDone();
    } catch (caught) {
      setError(caught);
    }
  };
  return (
    <div className="inline-form">
      <label>
        {title}
        <textarea rows={4} minLength={20} maxLength={20000} value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <button type="button" disabled={text.trim().length < 20} onClick={send}>
        {t("review.sendExplanation")}
      </button>
      {error !== null && <ErrorText error={error} />}
    </div>
  );
}
