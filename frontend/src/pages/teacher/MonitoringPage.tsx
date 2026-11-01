import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import { apiSend } from "../../api/client";
import type { GenAiMode, TaskSummary } from "../../api/types";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";

interface Board {
  criteria: Record<string, Record<string, number>>;
  difficulties: {
    verdicts: Record<string, number>;
    compile_error_kinds: Record<string, number>;
    low_criteria: Record<string, number>;
  };
  students: {
    user_id: number;
    full_name: string;
    submissions: number;
    solved: number;
    criteria: Record<string, string>;
  }[];
}

interface SolveRates {
  settings: { tolerance: number; min_students: number };
  tasks: {
    task_id: number;
    title: string;
    level: string | null;
    students: number;
    rate: number | null;
    expected: number | null;
    flagged: boolean;
    direction: "easier" | "harder" | null;
  }[];
}

interface Assignment {
  id: number;
  task_id: number;
  task_title: string;
  user_id: number;
  full_name: string | null;
  note: string;
  genai_mode: GenAiMode;
  last_verdict: string | null;
}

const CRITERIA = ["understanding", "algorithm", "correctness", "code_quality", "debugging", "explanation"];
const LEVELS = ["low", "mid", "high"] as const;

/** ФТ-04 group board, ФТ-20 solve rates, ФТ-05 individual tasks. */
export function MonitoringPage() {
  const { courseId } = useParams();
  const { t } = useTranslation();
  const board = useResource<Board>(`/api/courses/${courseId}/monitoring`);

  return (
    <>
      <section className="card">
        <h1>{t("monitoring.title")}</h1>
        <Status loading={board.loading} error={board.error} />
        {board.data && (
          <>
            <table aria-label={t("monitoring.criteria")}>
              <thead>
                <tr>
                  <th>{t("monitoring.criterion")}</th>
                  {LEVELS.map((l) => (
                    <th key={l}>{t(`levels.${l}`)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {CRITERIA.map((code) => (
                  <tr key={code}>
                    <td>{t(`review.criteria.${code}`)}</td>
                    {LEVELS.map((l) => (
                      <td key={l}>{board.data?.criteria[code]?.[l] ?? 0}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <h2>{t("monitoring.difficulties")}</h2>
            <ul>
              {Object.entries(board.data.difficulties.low_criteria).map(([code, n]) => (
                <li key={code}>
                  {t("monitoring.lowCriterion", { criterion: t(`review.criteria.${code}`), n })}
                </li>
              ))}
              {Object.entries(board.data.difficulties.verdicts).map(([v, n]) => (
                <li key={v}>
                  {t(`verdicts.${v}`)}: {n}
                </li>
              ))}
              {Object.entries(board.data.difficulties.compile_error_kinds).map(([kind, n]) => (
                <li key={kind}>
                  {t(`errorKind.${kind}`)}: {n}
                </li>
              ))}
            </ul>
            <h2>{t("monitoring.students")}</h2>
            <table>
              <thead>
                <tr>
                  <th>{t("activity.student")}</th>
                  <th>{t("monitoring.solved")}</th>
                  {CRITERIA.map((code) => (
                    <th key={code}>{t(`review.criteria.${code}`)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {board.data.students.map((s) => (
                  <tr key={s.user_id}>
                    <td>
                      <Link to={`/teacher/courses/${courseId}/students/${s.user_id}`}>{s.full_name}</Link>
                    </td>
                    <td>
                      {s.solved}/{s.submissions}
                    </td>
                    {CRITERIA.map((code) => (
                      <td key={code} className={s.criteria[code] === "low" ? "flag" : undefined}>
                        {s.criteria[code] ? t(`levels.${s.criteria[code]}`) : "—"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
      <SolveRatesTable courseId={Number(courseId)} />
      {board.data && <Assignments courseId={Number(courseId)} students={board.data.students} />}
    </>
  );
}

function SolveRatesTable({ courseId }: { courseId: number }) {
  const { t } = useTranslation();
  const rates = useResource<SolveRates>(`/api/courses/${courseId}/solve-rates`);
  if (!rates.data) return <Status loading={rates.loading} error={rates.error} />;
  const percent = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);
  return (
    <section className="card">
      <h2>{t("monitoring.solveRates")}</h2>
      <p className="muted">
        {t("monitoring.solveRatesHelp", {
          tolerance: Math.round(rates.data.settings.tolerance * 100),
          n: rates.data.settings.min_students,
        })}
      </p>
      <table>
        <thead>
          <tr>
            <th>{t("olympiad.problem")}</th>
            <th>{t("task.level")}</th>
            <th>{t("monitoring.students")}</th>
            <th>{t("monitoring.rate")}</th>
            <th>{t("monitoring.expected")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rates.data.tasks.map((row) => (
            <tr key={row.task_id} className={row.flagged ? "flag" : undefined}>
              <td>{row.title}</td>
              <td>{row.level ?? "—"}</td>
              <td>{row.students}</td>
              <td>{percent(row.rate)}</td>
              <td>{percent(row.expected)}</td>
              <td>{row.flagged && row.direction ? t(`monitoring.${row.direction}`) : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Assignments({ courseId, students }: { courseId: number; students: Board["students"] }) {
  const { t } = useTranslation();
  const assignments = useResource<Assignment[]>(`/api/courses/${courseId}/assignments`);
  const tasks = useResource<TaskSummary[]>(`/api/tasks?course_id=${courseId}&status=approved`);
  const [userId, setUserId] = useState("");
  const [taskId, setTaskId] = useState("");
  const [note, setNote] = useState("");
  const [mode, setMode] = useState<GenAiMode>("hints_only");
  const [error, setError] = useState<unknown>(null);

  const assign = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await apiSend("POST", `/api/courses/${courseId}/assignments`, {
        user_id: Number(userId),
        task_id: Number(taskId),
        note,
        genai_mode: mode,
      });
      setNote("");
      assignments.reload();
    } catch (caught) {
      setError(caught);
    }
  };

  const remove = async (id: number) => {
    try {
      await apiSend("DELETE", `/api/assignments/${id}`);
      assignments.reload();
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <section className="card">
      <h2>{t("assignments.title")}</h2>
      <form className="inline-form" onSubmit={assign}>
        <label>
          {t("activity.student")}
          <select required value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="" />
            {students.map((s) => (
              <option key={s.user_id} value={s.user_id}>
                {s.full_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("olympiad.problem")}
          <select required value={taskId} onChange={(e) => setTaskId(e.target.value)}>
            <option value="" />
            {tasks.data?.map((task) => (
              <option key={task.id} value={task.id}>
                {task.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("assignments.note")}
          <textarea rows={2} maxLength={5000} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <label>
          {t("assignments.mode")}
          <select value={mode} onChange={(e) => setMode(e.target.value as GenAiMode)}>
            {(["forbidden", "hints_only", "open"] as const).map((m) => (
              <option key={m} value={m}>
                {t(`genai.${m}`)}
              </option>
            ))}
          </select>
        </label>
        <button type="submit">{t("assignments.assign")}</button>
      </form>
      {error !== null && <ErrorText error={error} />}
      <ul>
        {assignments.data?.map((a) => (
          <li key={a.id}>
            {a.full_name}: {a.task_title} ({t(`genai.${a.genai_mode}`)}) —{" "}
            {a.last_verdict ? t(`verdicts.${a.last_verdict}`) : t("assignments.notStarted")}{" "}
            <button type="button" className="link" onClick={() => remove(a.id)}>
              {t("common.delete")}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
