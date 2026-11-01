import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiSend } from "../../api/client";
import type { Hint, OwnResult, OwnTest, Problem, StressResult } from "../../api/olympiad";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";

/** ОТ-06: own tests kept for the problem, all run with one button (as in CPEditor). */
export function OwnTestsPanel({
  taskId,
  sessionId,
  code,
  disabled,
}: {
  taskId: number;
  sessionId: string;
  code: string;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const tests = useResource<OwnTest[]>(`/api/olympiad/problems/${taskId}/my-tests`);
  const [input, setInput] = useState("");
  const [expected, setExpected] = useState("");
  const [results, setResults] = useState<Record<number, OwnResult>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const add = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await apiSend("POST", `/api/olympiad/problems/${taskId}/my-tests`, {
        input,
        expected_output: expected || null,
      });
      setInput("");
      setExpected("");
      tests.reload();
    } catch (caught) {
      setError(caught);
    }
  };

  const remove = async (id: number) => {
    try {
      await apiSend("DELETE", `/api/olympiad/my-tests/${id}`);
      tests.reload();
    } catch (caught) {
      setError(caught);
    }
  };

  const runAll = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await apiSend<OwnResult[]>("POST", `/api/sessions/${sessionId}/my-tests/run`, { code });
      setResults(Object.fromEntries(out.map((r) => [r.test_id, r])));
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card" aria-label={t("olympiad.ownTests")}>
      <h2>{t("olympiad.ownTests")}</h2>
      <Status loading={tests.loading} error={tests.error} />
      <ol>
        {tests.data?.map((test) => {
          const result = results[test.id];
          return (
            <li key={test.id}>
              <div className="row">
                <pre className="io">{test.input}</pre>
                {test.expected_output !== null && <pre className="io">{test.expected_output}</pre>}
                {result && <pre className="io">{result.output}</pre>}
              </div>
              {result && (
                <strong>
                  {result.verdict ? t(`verdicts.${result.verdict}`) : t(`runStatus.${result.status}`)}
                </strong>
              )}{" "}
              <button type="button" className="link" onClick={() => remove(test.id)}>
                {t("common.delete")}
              </button>
            </li>
          );
        })}
      </ol>
      <button type="button" disabled={disabled || busy || !tests.data?.length} onClick={runAll}>
        {t("olympiad.runAll")}
      </button>
      <form className="inline-form" onSubmit={add}>
        <label>
          {t("olympiad.testInput")}
          <textarea className="code" rows={3} required value={input} onChange={(e) => setInput(e.target.value)} />
        </label>
        <label>
          {t("olympiad.testAnswer")}
          <textarea className="code" rows={2} value={expected} onChange={(e) => setExpected(e.target.value)} />
        </label>
        <button type="submit">{t("olympiad.addTest")}</button>
      </form>
      {error !== null && <ErrorText error={error} />}
    </section>
  );
}

/** ОТ-06: compare with a slow correct solution on generated tests. */
export function StressPanel({ sessionId, code, disabled }: { sessionId: string; code: string; disabled: boolean }) {
  const { t } = useTranslation();
  const [brute, setBrute] = useState("");
  const [generator, setGenerator] = useState("");
  const [iterations, setIterations] = useState(10);
  const [result, setResult] = useState<StressResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const run = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await apiSend<StressResult>("POST", `/api/sessions/${sessionId}/stress`, {
          code,
          brute_code: brute,
          generator_code: generator,
          iterations,
        }),
      );
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <h2>{t("olympiad.stress")}</h2>
      <p className="muted">{t("olympiad.stressHelp")}</p>
      <form className="inline-form" onSubmit={run}>
        <label>
          {t("olympiad.brute")}
          <textarea className="code" rows={6} required value={brute} onChange={(e) => setBrute(e.target.value)} />
        </label>
        <label>
          {t("olympiad.generator")}
          <textarea className="code" rows={6} required value={generator} onChange={(e) => setGenerator(e.target.value)} />
        </label>
        <label>
          {t("olympiad.iterations")}
          <input
            type="number"
            min={1}
            max={20}
            value={iterations}
            onChange={(e) => setIterations(Number(e.target.value))}
          />
        </label>
        <button type="submit" disabled={disabled || busy || !code.trim()}>
          {t("olympiad.runStress")}
        </button>
      </form>
      {error !== null && <ErrorText error={error} />}
      {result && (
        <div role="status">
          <p>
            <strong>{t(`olympiad.stressStatus.${result.status}`, { n: result.iterations })}</strong>
          </p>
          {result.input && (
            <>
              <h3>{t("olympiad.testInput")}</h3>
              <pre className="io">{result.input}</pre>
            </>
          )}
          {result.status === "mismatch" && (
            <div className="row">
              <div>
                <h3>{t("olympiad.bruteAnswer")}</h3>
                <pre className="io">{result.expected}</pre>
              </div>
              <div>
                <h3>{t("olympiad.yourAnswer")}</h3>
                <pre className="io">{result.actual}</pre>
              </div>
            </div>
          )}
          {result.detail && <pre className="io">{result.detail}</pre>}
        </div>
      )}
    </section>
  );
}

/** ОТ-05: the tutorial after an hour on the problem; hints step by step, never code. */
export function ProblemExtras({
  taskId,
  sessionId,
  code,
  language,
}: {
  taskId: number;
  sessionId: string;
  code: string;
  language: "kk" | "ru";
}) {
  const { t } = useTranslation();
  const problem = useResource<Problem>(`/api/olympiad/problems/${taskId}`);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (!problem.data) return <Status loading={problem.loading} error={problem.error} />;
  const p = problem.data;

  const ask = async () => {
    setBusy(true);
    setError(null);
    try {
      await apiSend<Hint>("POST", `/api/olympiad/problems/${taskId}/hints`, {
        session_id: sessionId,
        code,
        ui_language: language,
      });
      problem.reload();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card" aria-label={t("olympiad.helpTitle")}>
      <h2>{t("olympiad.helpTitle")}</h2>
      <p className="muted">{t("olympiad.minutesSpent", { n: p.minutes_spent })}</p>
      <h3>{t("olympiad.editorial")}</h3>
      {p.editorial_available ? (
        <p className="statement">{p.editorial_md || t("olympiad.noEditorial")}</p>
      ) : (
        <p className="muted">
          {t("olympiad.editorialLocked")}
          {p.editorial_opens_at && ` ${new Date(p.editorial_opens_at).toLocaleTimeString()}`}
        </p>
      )}
      <h3>{t("olympiad.hints")}</h3>
      {p.in_contest ? (
        <p className="muted">{t("olympiad.aiOffInContest")}</p>
      ) : (
        <>
          <ol>
            {p.hints.map((h) => (
              <li key={h.level}>
                <span className="badge">AI</span> {t(`olympiad.hintLevel.${h.level}`)}: {h.answer}
              </li>
            ))}
          </ol>
          {p.next_hint_level !== null ? (
            <button type="button" disabled={busy || p.next_hint_at !== null} onClick={ask}>
              {t("olympiad.askHint", { step: t(`olympiad.hintLevel.${p.next_hint_level}`) })}
            </button>
          ) : (
            <p className="muted">{t("olympiad.noMoreHints")}</p>
          )}
          {p.next_hint_at && (
            <p className="muted">
              {t("olympiad.hintAt")} {new Date(p.next_hint_at).toLocaleTimeString()}
            </p>
          )}
        </>
      )}
      {error !== null && <ErrorText error={error} />}
    </section>
  );
}
