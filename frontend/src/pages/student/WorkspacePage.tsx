import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { apiGet, apiSend } from "../../api/client";
import type {
  RunOutput,
  SubmissionResult,
  TestsOutput,
  WorkSession,
} from "../../api/types";
import { CodeEditor } from "../../components/CodeEditor";
import { ErrorText, Status } from "../../components/Status";
import { AssistantPanel } from "./AssistantPanel";
import { OwnTestsPanel, ProblemExtras, StressPanel } from "./OlympiadTools";
import { useAuth } from "../../auth/AuthContext";
import { flushLeftovers, sendEvents, TraceRecorder } from "../../workspace/TraceRecorder";

const SNAPSHOT_DELAY_MS = 2000;
const POLL_MS = 1500;
const POLL_LIMIT = 200; // about five minutes

/** Task workspace (ФТ-24): editor, run, tests, submission with explanation (ФТ-27).
 *
 * `olympiad`: practice on a bank problem or a contest problem (spec 4, 10): own tests and
 * the stress test (ОТ-06), no explanation, the tutorial and hints instead of the assistant
 * in practice (ОТ-05), no AI at all in a contest (ОТ-02). */
export function WorkspacePage({ olympiad = false }: { olympiad?: boolean }) {
  const { assessmentId, taskId } = useParams();
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const userId = user?.id ?? 0;
  const [session, setSession] = useState<WorkSession | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [closed, setClosed] = useState(false);
  const [code, setCode] = useState("");
  const recorder = useRef<TraceRecorder | null>(null);
  const opened = useRef(false);
  const snapshotTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (opened.current) return; // StrictMode runs effects twice; open one session only
    opened.current = true;
    apiSend<WorkSession>("POST", "/api/sessions", {
      task_id: Number(taskId),
      assessment_id: assessmentId ? Number(assessmentId) : null,
    }).then(
      (opened) => {
        const rec = new TraceRecorder(userId, opened.session_id, sendEvents, () => setClosed(true));
        rec.start();
        recorder.current = rec;
        void flushLeftovers(sendEvents, userId, opened.session_id);
        setSession(opened);
        setCode(opened.code);
      },
      (caught: unknown) => setError(caught),
    );
  }, [assessmentId, taskId, userId]);

  useEffect(() => {
    const lost = () => recorder.current?.record("focus_lost");
    const back = () => recorder.current?.record("focus_back");
    const visibility = () => (document.hidden ? lost() : back());
    window.addEventListener("blur", lost);
    window.addEventListener("focus", back);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      window.removeEventListener("blur", lost);
      window.removeEventListener("focus", back);
      document.removeEventListener("visibilitychange", visibility);
      recorder.current?.stop();
      void recorder.current?.flush();
    };
  }, []);

  const snapshotNow = useCallback((current: string) => {
    if (snapshotTimer.current) clearTimeout(snapshotTimer.current);
    snapshotTimer.current = null;
    recorder.current?.record("snapshot", { code: current });
    void recorder.current?.flush();
  }, []);

  const handleChange = (next: string) => {
    setCode(next);
    if (snapshotTimer.current) clearTimeout(snapshotTimer.current);
    snapshotTimer.current = setTimeout(() => snapshotNow(next), SNAPSHOT_DELAY_MS);
  };

  const handlePaste = (length: number, lines: number) =>
    recorder.current?.record("paste", { length, lines });

  if (!session) return <Status loading={error === null} error={error} />;

  return (
    <>
      <section className="card">
        <h1>{session.task.title}</h1>
        {session.ends_at && (
          <p className="muted">
            {t("workspace.endsAt")}: {new Date(session.ends_at).toLocaleString()}
          </p>
        )}
        <p className="statement">{session.task.statement_md}</p>
        {session.task.input_format && (
          <>
            <h3>{t("task.inputFormat")}</h3>
            <p className="statement">{session.task.input_format}</p>
          </>
        )}
        {session.task.output_format && (
          <>
            <h3>{t("task.outputFormat")}</h3>
            <p className="statement">{session.task.output_format}</p>
          </>
        )}
        <p className="muted">
          {t("workspace.limits", {
            time: session.task.time_limit_ms,
            memory: Math.round(session.task.memory_limit_kb / 1024),
          })}
        </p>
        {session.task.examples.map((ex) => (
          <div key={ex.position} className="row">
            <pre className="io">{ex.input}</pre>
            <pre className="io">{ex.expected_output}</pre>
          </div>
        ))}
      </section>

      {closed && (
        <p role="alert" className="card">
          {t("workspace.sessionClosed")}
        </p>
      )}

      <section className="card">
        <CodeEditor value={code} onChange={handleChange} onPaste={handlePaste} label={t("workspace.editor")} />
        <RunPanel sessionId={session.session_id} code={code} disabled={closed} beforeAction={() => snapshotNow(code)} />
        <SubmitPanel
          sessionId={session.session_id}
          code={code}
          disabled={closed}
          language={i18n.language === "ru" ? "ru" : "kk"}
          beforeAction={() => snapshotNow(code)}
          withExplanation={!olympiad}
        />
      </section>
      {olympiad ? (
        <>
          <OwnTestsPanel taskId={session.task.id} sessionId={session.session_id} code={code} disabled={closed} />
          <StressPanel sessionId={session.session_id} code={code} disabled={closed} />
          {session.assessment_id === null && (
            <ProblemExtras
              taskId={session.task.id}
              sessionId={session.session_id}
              code={code}
              language={i18n.language === "ru" ? "ru" : "kk"}
            />
          )}
        </>
      ) : (
        <AssistantPanel sessionId={session.session_id} mode={session.genai_mode} code={code} disabled={closed} />
      )}
    </>
  );
}

function RunPanel({
  sessionId,
  code,
  disabled,
  beforeAction,
}: {
  sessionId: string;
  code: string;
  disabled: boolean;
  beforeAction: () => void;
}) {
  const { t } = useTranslation();
  const [stdin, setStdin] = useState("");
  const [run, setRun] = useState<RunOutput | null>(null);
  const [tests, setTests] = useState<TestsOutput | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const act = async (kind: "run" | "test") => {
    beforeAction();
    setBusy(true);
    setError(null);
    try {
      if (kind === "run") {
        setTests(null);
        setRun(await apiSend<RunOutput>("POST", `/api/sessions/${sessionId}/run`, { code, stdin }));
      } else {
        setRun(null);
        setTests(await apiSend<TestsOutput>("POST", `/api/sessions/${sessionId}/test`, { code }));
      }
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="run-panel">
      <label>
        {t("workspace.stdin")}
        <textarea className="code" rows={3} value={stdin} onChange={(e) => setStdin(e.target.value)} />
      </label>
      <div className="row">
        <button type="button" disabled={disabled || busy} onClick={() => act("run")}>
          {t("workspace.run")}
        </button>
        <button type="button" disabled={disabled || busy} onClick={() => act("test")}>
          {t("workspace.runTests")}
        </button>
      </div>
      {error !== null && <ErrorText error={error} />}
      {run && (
        <div aria-label={t("workspace.output")}>
          <p>
            {t(`runStatus.${run.status}`)}
            {run.time_ms !== null && ` · ${run.time_ms} ms`}
          </p>
          {run.compile_output && <pre className="io">{run.compile_output}</pre>}
          {run.stdout && <pre className="io">{run.stdout}</pre>}
          {run.stderr && <pre className="io">{run.stderr}</pre>}
        </div>
      )}
      {tests && (
        <div>
          {tests.compile_output && <pre className="io">{tests.compile_output}</pre>}
          <ul>
            {tests.results.map((r) => (
              <li key={r.position}>
                {t("workspace.testN", { n: r.position })}: <strong>{t(`verdicts.${r.verdict}`)}</strong>
                {r.verdict === "WA" && (
                  <div className="row">
                    <pre className="io">{r.expected_output}</pre>
                    <pre className="io">{r.actual_output}</pre>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function SubmitPanel({
  sessionId,
  code,
  disabled,
  language,
  beforeAction,
  withExplanation,
}: {
  sessionId: string;
  code: string;
  disabled: boolean;
  language: "kk" | "ru";
  beforeAction: () => void;
  withExplanation: boolean;
}) {
  const { t } = useTranslation();
  const [explanation, setExplanation] = useState("");
  const [submission, setSubmission] = useState<SubmissionResult | null>(null);
  const [answers, setAnswers] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const polls = useRef(0);

  useEffect(() => {
    if (!submission || submission.status === "done" || submission.status === "error") return;
    if (polls.current >= POLL_LIMIT) return;
    const timer = setTimeout(() => {
      polls.current += 1;
      apiGet<SubmissionResult>(`/api/submissions/${submission.id}`).then(setSubmission, setError);
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [submission]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    beforeAction();
    setError(null);
    setSaved(false);
    try {
      const created = await apiSend<SubmissionResult>("POST", `/api/sessions/${sessionId}/submit`, {
        code,
        ...(withExplanation ? { explanation } : {}),
        ui_language: language,
      });
      polls.current = 0;
      setSubmission(created);
      setAnswers((created.questions ?? []).map(() => ""));
    } catch (caught) {
      setError(caught);
    }
  };

  const sendAnswers = async (event: FormEvent) => {
    event.preventDefault();
    if (!submission) return;
    try {
      setSubmission(
        await apiSend<SubmissionResult>("PUT", `/api/submissions/${submission.id}/answers`, { answers }),
      );
      setSaved(true);
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <>
      <form className="inline-form" onSubmit={submit}>
        <h2>{t("workspace.submitTitle")}</h2>
        {withExplanation && (
          <label>
            {t("workspace.explanation")}
            <textarea
              required
              rows={4}
              maxLength={20000}
              value={explanation}
              onChange={(e) => setExplanation(e.target.value)}
            />
          </label>
        )}
        <button type="submit" disabled={disabled || !code.trim()}>
          {t("workspace.submit")}
        </button>
      </form>
      {error !== null && <ErrorText error={error} />}
      {submission && (
        <div className="submission" role="status">
          {submission.status === "done" && submission.verdict ? (
            <p>
              {t("workspace.verdict")}: <strong>{t(`verdicts.${submission.verdict}`)}</strong> ·{" "}
              {t("workspace.passed", { passed: submission.tests_passed, total: submission.tests_total })}
            </p>
          ) : (
            <p>{t(`submissionStatus.${submission.status}`)}</p>
          )}
          {submission.compile_output && <pre className="io">{submission.compile_output}</pre>}
        </div>
      )}
      {submission && (submission.questions?.length ?? 0) > 0 && (
        <form className="inline-form" onSubmit={sendAnswers}>
          <h3>{t("workspace.questionsTitle")}</h3>
          {submission.questions.map((q, i) => (
            <label key={i}>
              {q.question}
              <textarea
                required
                rows={2}
                value={answers[i] ?? ""}
                onChange={(e) => setAnswers(answers.map((a, j) => (j === i ? e.target.value : a)))}
              />
            </label>
          ))}
          <button type="submit" disabled={disabled}>
            {t("workspace.sendAnswers")}
          </button>
          {saved && <p>{t("common.saved")}</p>}
        </form>
      )}
    </>
  );
}
