import { useTranslation } from "react-i18next";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { apiGet, apiSend, downloadFile } from "../../api/client";

import type { Assessment, StudentActivity, TaskSummary } from "../../api/types";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";

/**
 * Assessment progress for the teacher: last verdicts and integrity marks (ФТ-29).
 * Marks are hints for the teacher, not evidence; students never see them.
 */
export function ActivityPage() {
  const { assessmentId } = useParams();
  const { t } = useTranslation();
  const assessment = useResource<Assessment>(`/api/assessments/${assessmentId}`);
  const activity = useResource<StudentActivity[]>(`/api/assessments/${assessmentId}/activity`);
  const tasks = useResource<TaskSummary[]>(
    assessment.data ? `/api/tasks?course_id=${assessment.data.course_id}` : null,
  );

  if (!assessment.data) return <Status loading={assessment.loading} error={assessment.error} />;
  const titles = new Map((tasks.data ?? []).map((task) => [task.id, task.title]));

  return (
    <section className="card">
      <h1>{assessment.data.title}</h1>
      <p className="muted">{t("activity.hint")}</p>
      <AnalysisSettings assessmentId={Number(assessmentId)} />
      <PilotData assessmentId={Number(assessmentId)} />
      <ProcessReport assessmentId={Number(assessmentId)} />
      <Status loading={activity.loading} error={activity.error} />
      <table>
        <thead>
          <tr>
            <th>{t("activity.student")}</th>
            {assessment.data.task_ids.map((id) => (
              <th key={id}>{titles.get(id) ?? `#${id}`}</th>
            ))}
            <th>{t("activity.largePastes")}</th>
            <th>{t("activity.pastedChars")}</th>
            <th>{t("activity.focusLost")}</th>
            <th>{t("activity.lateEvents")}</th>
            <th>{t("activity.sessions")}</th>
          </tr>
        </thead>
        <tbody>
          {activity.data?.map((row) => (
            <tr key={row.user_id}>
              <td>{row.full_name}</td>
              {assessment.data!.task_ids.map((id) => {
                const verdict = row.last_verdicts[String(id)];
                const submission = row.last_submissions[String(id)];
                return (
                  <td key={id}>
                    {submission ? (
                      <Link to={`/teacher/submissions/${submission}`}>{verdict ? t(`verdicts.${verdict}`) : "…"}</Link>
                    ) : (
                      "—"
                    )}
                  </td>
                );
              })}
              <td className={row.large_pastes > 0 ? "flag" : undefined}>{row.large_pastes}</td>
              <td>{row.pasted_chars}</td>
              <td>{row.focus_lost}</td>
              <td className={row.late_events > 0 ? "flag" : undefined}>{row.late_events}</td>
              <td>
                {row.sessions.map((sid, i) => (
                  <Link key={sid} to={`/teacher/sessions/${sid}/replay`} title={t("replay.title")}>
                    {i > 0 && ", "}▶{i + 1}
                  </Link>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

const OPTIONAL_DATA = [
  "static_analysis",
  "process_metrics",
  "student_explanation",
  "genai_log",
  "book_fragments",
] as const;

/** ФТ-36: which data the AI analysis of this assessment uses. */
function AnalysisSettings({ assessmentId }: { assessmentId: number }) {
  const { t } = useTranslation();
  const config = useResource<{ excluded: string[]; note: string }>(`/api/assessments/${assessmentId}/analysis`);
  const [saved, setSaved] = useState(false);
  if (!config.data) return null;
  const excluded = new Set(config.data.excluded);

  const toggle = async (name: string, used: boolean) => {
    const next = new Set(excluded);
    if (used) next.delete(name);
    else next.add(name);
    await apiSend("PUT", `/api/assessments/${assessmentId}/analysis`, {
      excluded: [...next],
      note: config.data?.note ?? "",
    });
    setSaved(true);
    config.reload();
  };

  return (
    <fieldset className="analysis-settings">
      <legend>{t("activity.analysisData")}</legend>
      {OPTIONAL_DATA.map((name) => (
        <label key={name} className="checkbox">
          <input type="checkbox" checked={!excluded.has(name)} onChange={(e) => toggle(name, e.target.checked)} />
          {t(`activity.data.${name}`)}
        </label>
      ))}
      {saved && <p role="status">{t("common.saved")}</p>}
    </fieldset>
  );
}

interface Stats {
  n: number;
  pearson: number | null;
  spearman: number | null;
  mae: number | null;
  md: number | null;
}

/** ФТ-49 (core): AI and teacher grades side by side, and their agreement (spec 16). */
function PilotData({ assessmentId }: { assessmentId: number }) {
  const { t } = useTranslation();
  const [stats, setStats] = useState<Record<string, Stats> | null>(null);
  const [error, setError] = useState<unknown>(null);
  const run = (action: () => Promise<void>) => () => {
    setError(null);
    action().catch(setError);
  };
  const exportCsv = run(() =>
    downloadFile(`/api/assessments/${assessmentId}/export.csv`, `assessment-${assessmentId}.csv`),
  );
  const exportXlsx = run(() =>
    downloadFile(`/api/assessments/${assessmentId}/export.xlsx`, `assessment-${assessmentId}.xlsx`),
  );
  const loadStats = run(async () =>
    setStats(await apiGet<Record<string, Stats>>(`/api/assessments/${assessmentId}/agreement`)),
  );

  return (
    <div className="row">
      <button type="button" onClick={exportCsv}>
        {t("activity.export")}
      </button>
      <button type="button" onClick={exportXlsx}>
        {t("activity.exportXlsx")}
      </button>
      <button type="button" onClick={loadStats}>
        {t("activity.agreement")}
      </button>
      {error !== null && <ErrorText error={error} />}
      {stats && (
        <table aria-label={t("activity.agreement")}>
          <thead>
            <tr>
              <th />
              <th>n</th>
              <th>Pearson</th>
              <th>Spearman</th>
              <th>MAE</th>
              <th>MD</th>
            </tr>
          </thead>
          <tbody>
            {(["S", "F", "E", "A"] as const).map((key) => {
              const row = stats[key];
              return (
                <tr key={key}>
                  <td>{key}</td>
                  <td>{row?.n}</td>
                  <td>{row?.pearson ?? "—"}</td>
                  <td>{row?.spearman ?? "—"}</td>
                  <td>{row?.mae ?? "—"}</td>
                  <td>{row?.md ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

interface ProcessRow {
  user_id: number;
  full_name: string;
  task_id: number;
  verdict: string | null;
  attempts: number;
  compile_errors: number;
  repeated_compile_errors: number;
  fix_minutes: number;
  minutes: number;
  stage_events: Record<string, number>;
}

interface GenAiRow {
  user_id: number;
  task_id: number;
  requests: number;
  blocked: number;
  max_similarity_to_final_code: number;
}

/** ФТ-33 process metrics and ФТ-38 GenAI use of each student's latest submission. */
function ProcessReport({ assessmentId }: { assessmentId: number }) {
  const { t } = useTranslation();
  const process = useResource<ProcessRow[]>(`/api/assessments/${assessmentId}/process`);
  const genai = useResource<{ by_stage: Record<string, number>; students: GenAiRow[] }>(
    `/api/assessments/${assessmentId}/genai`,
  );
  if (!process.data) return <Status loading={process.loading} error={process.error} />;
  const ai = new Map(genai.data?.students.map((g) => [`${g.user_id}:${g.task_id}`, g]));
  return (
    <div>
      <h2>{t("process.title")}</h2>
      <table aria-label={t("process.title")}>
        <thead>
          <tr>
            <th>{t("activity.student")}</th>
            <th>{t("process.attempts")}</th>
            <th>{t("process.compileErrors")}</th>
            <th>{t("process.repeated")}</th>
            <th>{t("process.fixMinutes")}</th>
            <th>{t("process.minutes")}</th>
            <th>{t("process.aiRequests")}</th>
            <th>{t("process.aiSimilarity")}</th>
          </tr>
        </thead>
        <tbody>
          {process.data.map((row) => {
            const g = ai.get(`${row.user_id}:${row.task_id}`);
            return (
              <tr key={`${row.user_id}:${row.task_id}`}>
                <td>{row.full_name}</td>
                <td>{row.attempts}</td>
                <td>{row.compile_errors}</td>
                <td>{row.repeated_compile_errors}</td>
                <td>{row.fix_minutes}</td>
                <td>{row.minutes}</td>
                <td>{g ? `${g.requests} (${g.blocked})` : "—"}</td>
                <td className={g && g.max_similarity_to_final_code >= 0.8 ? "flag" : undefined}>
                  {g ? `${Math.round(g.max_similarity_to_final_code * 100)}%` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {genai.data && Object.keys(genai.data.by_stage).length > 0 && (
        <p className="muted">
          {t("process.aiByStage")}:{" "}
          {Object.entries(genai.data.by_stage)
            .map(([stage, n]) => `${t(`stage.${stage}`)} ${n}`)
            .join(", ")}
        </p>
      )}
    </div>
  );
}
