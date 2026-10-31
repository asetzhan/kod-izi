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
              <td>{row.sessions.length}</td>
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
  const loadStats = run(async () =>
    setStats(await apiGet<Record<string, Stats>>(`/api/assessments/${assessmentId}/agreement`)),
  );

  return (
    <div className="row">
      <button type="button" onClick={exportCsv}>
        {t("activity.export")}
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
