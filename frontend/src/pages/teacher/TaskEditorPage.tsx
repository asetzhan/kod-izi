import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { apiSend } from "../../api/client";
import {
  type Course,
  FEATURE_CODES,
  type FeatureScores,
  type LevelRule,
  type LevelSuggestion,
  type Task,
  type TaskLevel,
  type TestCase,
} from "../../api/types";
import { levelFor } from "../../api/levels";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";

const EMPTY_TASK = {
  title: "",
  topic_id: null as number | null,
  statement_md: "",
  input_format: "",
  output_format: "",
  time_limit_ms: 1000,
  memory_limit_kb: 262144,
  reference_solution: "",
  reference_language: "cpp17",
  source_url: null as string | null,
  source_note: "",
  tests: [] as TestCase[],
  knowledge_component_ids: [] as number[],
};
type TaskForm = typeof EMPTY_TASK;

function toForm(task: Task): TaskForm {
  return {
    title: task.title,
    topic_id: task.topic_id,
    statement_md: task.statement_md,
    input_format: task.input_format,
    output_format: task.output_format,
    time_limit_ms: task.time_limit_ms,
    memory_limit_kb: task.memory_limit_kb,
    reference_solution: task.reference_solution,
    reference_language: task.reference_language,
    source_url: task.source_url,
    source_note: task.source_note,
    tests: task.tests.map(({ input, expected_output, is_hidden }) => ({
      input,
      expected_output,
      is_hidden,
    })),
    knowledge_component_ids: task.knowledge_component_ids,
  };
}

/** Task editor: content, tests, knowledge components (ФТ-10, ФТ-18), level (ФТ-19). */
export function TaskEditorPage() {
  const { taskId, courseId: newCourseId } = useParams();
  const existing = useResource<Task>(taskId ? `/api/tasks/${taskId}` : null);
  if (taskId && !existing.data) return <Status loading={existing.loading} error={existing.error} />;
  const courseId = existing.data?.course_id ?? Number(newCourseId);
  return (
    <TaskEditor
      key={existing.data?.id ?? "new"}
      courseId={courseId}
      task={existing.data}
      onSaved={existing.reload}
    />
  );
}

function TaskEditor({
  courseId,
  task,
  onSaved,
}: {
  courseId: number;
  task: Task | undefined;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const course = useResource<Course>(`/api/courses/${courseId}`);
  const [form, setForm] = useState<TaskForm>(task ? toForm(task) : EMPTY_TASK);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  const set = <K extends keyof TaskForm>(key: K, value: TaskForm[K]) => {
    setSaved(false);
    setForm((f) => ({ ...f, [key]: value }));
  };
  const setTest = (index: number, change: Partial<TestCase>) =>
    set("tests", form.tests.map((test, i) => (i === index ? { ...test, ...change } : test)));

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      if (task) {
        await apiSend("PUT", `/api/tasks/${task.id}`, form);
        setSaved(true);
        onSaved();
      } else {
        const created = await apiSend<Task>("POST", "/api/tasks", { ...form, course_id: courseId });
        navigate(`/teacher/tasks/${created.id}`, { replace: true });
      }
    } catch (caught) {
      setError(caught);
    }
  };

  const components = course.data?.topics.flatMap((tp) =>
    tp.knowledge_components.map((kc) => ({ ...kc, topic: tp.code })),
  );
  const canEdit = course.data?.can_edit ?? false;

  return (
    <>
      <form className="card task-form" onSubmit={save}>
        <h1>{task ? task.title : t("task.new")}</h1>
        {task && (
          <p>
            {t("task.status")}: <strong>{t(`taskStatus.${task.status}`)}</strong>
            {task.external_key && <> · {task.external_key}</>}
          </p>
        )}
        {task?.source_note && <p className="muted">{task.source_note}</p>}
        <fieldset disabled={!canEdit}>
          <label>
            {t("task.title")}
            <input required maxLength={200} value={form.title} onChange={(e) => set("title", e.target.value)} />
          </label>
          <label>
            {t("task.topic")}
            <select
              value={form.topic_id ?? ""}
              onChange={(e) => set("topic_id", e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">—</option>
              {course.data?.topics.map((tp) => (
                <option key={tp.id} value={tp.id}>
                  {tp.code} {tp.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("task.statement")}
            <textarea required rows={6} value={form.statement_md} onChange={(e) => set("statement_md", e.target.value)} />
          </label>
          <label>
            {t("task.inputFormat")}
            <textarea rows={2} value={form.input_format} onChange={(e) => set("input_format", e.target.value)} />
          </label>
          <label>
            {t("task.outputFormat")}
            <textarea rows={2} value={form.output_format} onChange={(e) => set("output_format", e.target.value)} />
          </label>
          <div className="row">
            <label>
              {t("task.timeLimit")}
              <input
                type="number"
                min={100}
                max={20000}
                value={form.time_limit_ms}
                onChange={(e) => set("time_limit_ms", Number(e.target.value))}
              />
            </label>
            <label>
              {t("task.memoryLimit")}
              <input
                type="number"
                min={16384}
                max={1048576}
                value={form.memory_limit_kb}
                onChange={(e) => set("memory_limit_kb", Number(e.target.value))}
              />
            </label>
          </div>
          <label>
            {t("task.referenceSolution")}
            <textarea
              rows={8}
              className="code"
              value={form.reference_solution}
              onChange={(e) => set("reference_solution", e.target.value)}
            />
          </label>

          <h2>{t("task.tests")}</h2>
          {form.tests.map((test, i) => (
            <div key={i} className="test-row">
              <label>
                {t("task.testInput", { n: i + 1 })}
                <textarea rows={2} className="code" value={test.input} onChange={(e) => setTest(i, { input: e.target.value })} />
              </label>
              <label>
                {t("task.testOutput")}
                <textarea
                  rows={2}
                  className="code"
                  value={test.expected_output}
                  onChange={(e) => setTest(i, { expected_output: e.target.value })}
                />
              </label>
              <label className="checkbox">
                <input type="checkbox" checked={test.is_hidden} onChange={(e) => setTest(i, { is_hidden: e.target.checked })} />
                {t("task.hidden")}
              </label>
              <button type="button" onClick={() => set("tests", form.tests.filter((_, j) => j !== i))}>
                {t("common.remove")}
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => set("tests", [...form.tests, { input: "", expected_output: "", is_hidden: true }])}
          >
            {t("task.addTest")}
          </button>

          <h2>{t("course.knowledgeComponents")}</h2>
          {components?.map((kc) => (
            <label key={kc.id} className="checkbox">
              <input
                type="checkbox"
                checked={form.knowledge_component_ids.includes(kc.id)}
                onChange={(e) =>
                  set(
                    "knowledge_component_ids",
                    e.target.checked
                      ? [...form.knowledge_component_ids, kc.id]
                      : form.knowledge_component_ids.filter((id) => id !== kc.id),
                  )
                }
              />
              {kc.topic} · {kc.name}
            </label>
          ))}
        </fieldset>
        {canEdit && <button type="submit">{t("common.save")}</button>}
        {saved && <p role="status">{t("common.saved")}</p>}
        {error !== null && <ErrorText error={error} />}
      </form>
      {task && <LevelPanel task={task} canEdit={canEdit} onChanged={onSaved} />}
    </>
  );
}

function LevelPanel({ task, canEdit, onChanged }: { task: Task; canEdit: boolean; onChanged: () => void }) {
  const { t } = useTranslation();
  const rule = useResource<LevelRule>("/api/settings/task-level-rule");
  const [scores, setScores] = useState<FeatureScores>(() =>
    Object.fromEntries(FEATURE_CODES.map((c) => [c, task.features[c] ?? 0])) as FeatureScores,
  );
  const [override, setOverride] = useState<TaskLevel | "">("");
  const [rationale, setRationale] = useState(task.level_rationale);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const run = async (action: () => Promise<void>) => {
    setError(null);
    setMessage(null);
    try {
      await action();
    } catch (caught) {
      setError(caught);
    }
  };

  const suggest = () =>
    run(async () => {
      const s = await apiSend<LevelSuggestion>("POST", `/api/tasks/${task.id}/level-suggestion`);
      setScores(s.features);
      setRationale(s.rationale);
      setMessage(t(s.saved ? "level.suggested" : "level.suggestedNotSaved", { level: s.level }));
      if (s.saved) onChanged();
    });

  const confirm = () =>
    run(async () => {
      await apiSend("PUT", `/api/tasks/${task.id}/level`, {
        features: scores,
        level: override || null,
        rationale,
      });
      setMessage(t("level.confirmed"));
      onChanged();
    });

  const approve = () =>
    run(async () => {
      await apiSend("POST", `/api/tasks/${task.id}/approve`);
      setMessage(t("task.approvedMessage"));
      onChanged();
    });

  const preview = rule.data ? levelFor(rule.data, scores) : undefined;

  return (
    <section className="card">
      <h2>{t("level.title")}</h2>
      <p>
        {t("task.level")}: <strong>{task.level ?? "—"}</strong> ({t(`levelStatus.${task.level_status}`)})
      </p>
      <fieldset disabled={!canEdit}>
        {FEATURE_CODES.map((code) => (
          <label key={code}>
            {t(`level.features.${code}`)}
            <select
              aria-label={t(`level.features.${code}`)}
              value={scores[code]}
              onChange={(e) => setScores({ ...scores, [code]: Number(e.target.value) })}
            >
              {[0, 1, 2].map((v) => (
                <option key={v} value={v}>
                  {v} — {t(`level.scale.${code}.${v}`)}
                </option>
              ))}
            </select>
          </label>
        ))}
        <p>
          {t("level.byRule")}: <strong data-testid="level-preview">{preview ?? "—"}</strong>
        </p>
        <label>
          {t("level.override")}
          <select value={override} onChange={(e) => setOverride(e.target.value as TaskLevel | "")}>
            <option value="">{t("level.noOverride")}</option>
            {(["I", "II", "III", "IV"] as const).map((lv) => (
              <option key={lv} value={lv}>
                {lv}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("level.rationale")}
          <textarea rows={2} value={rationale} onChange={(e) => setRationale(e.target.value)} />
        </label>
      </fieldset>
      {canEdit && (
        <div className="row">
          <button type="button" onClick={suggest}>
            {t("level.suggest")}
          </button>
          <button type="button" onClick={confirm}>
            {t("level.confirm")}
          </button>
          {task.status === "draft" && (
            <button type="button" onClick={approve}>
              {t("task.approve")}
            </button>
          )}
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {error !== null && <ErrorText error={error} />}
    </section>
  );
}
