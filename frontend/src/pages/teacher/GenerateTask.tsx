import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { apiSend } from "../../api/client";
import type { Material, TaskLevel, TaskSummary, Topic } from "../../api/types";
import { useResource } from "../../api/useResource";
import { ErrorText } from "../../components/Status";

interface Chapter {
  chapter: string;
  first_page: number | null;
  last_page: number | null;
}

interface Generated {
  task: TaskSummary;
  dropped_tests: number;
}

/** ФТ-21: the LLM drafts a task and its tests, from a topic or a chosen book chapter. */
export function GenerateTask({ courseId, topics }: { courseId: number; topics: Topic[] }) {
  const { t, i18n } = useTranslation();
  const materials = useResource<Material[]>(`/api/courses/${courseId}/materials`);
  const [topicId, setTopicId] = useState("");
  const [level, setLevel] = useState<TaskLevel>("I");
  const [materialId, setMaterialId] = useState("");
  const [chapter, setChapter] = useState("");
  const [result, setResult] = useState<Generated | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const material = materials.data?.find((m) => String(m.id) === materialId);
  const version = material?.versions.find((v) => v.status === "ready");
  const chapters = useResource<Chapter[]>(
    material && version ? `/api/materials/${material.id}/versions/${version.id}/chapters` : null,
  );

  const generate = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await apiSend<Generated>("POST", `/api/courses/${courseId}/tasks/generate`, {
          topic_id: Number(topicId),
          level,
          language: i18n.language === "ru" ? "ru" : "kk",
          ...(version && chapter ? { version_id: version.id, chapter } : {}),
        }),
      );
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="inline-form" onSubmit={generate} aria-label={t("generate.title")}>
      <h3>{t("generate.title")}</h3>
      <p className="muted">{t("generate.help")}</p>
      <label>
        {t("generate.topic")}
        <select required value={topicId} onChange={(e) => setTopicId(e.target.value)}>
          <option value="" />
          {topics.map((tp) => (
            <option key={tp.id} value={tp.id}>
              {tp.code} {tp.title}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("task.level")}
        <select value={level} onChange={(e) => setLevel(e.target.value as TaskLevel)}>
          {(["I", "II", "III"] as const).map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("generate.book")}
        <select
          value={materialId}
          onChange={(e) => {
            setMaterialId(e.target.value);
            setChapter("");
          }}
        >
          <option value="">{t("generate.noBook")}</option>
          {materials.data
            ?.filter((m) => m.versions.some((v) => v.status === "ready"))
            .map((m) => (
              <option key={m.id} value={m.id}>
                {m.title}
              </option>
            ))}
        </select>
      </label>
      {material && (
        <label>
          {t("generate.chapter")}
          <select value={chapter} onChange={(e) => setChapter(e.target.value)}>
            <option value="" />
            {chapters.data?.map((c) => (
              <option key={c.chapter} value={c.chapter}>
                {c.chapter || t("generate.untitled")}
                {c.first_page !== null && ` (${c.first_page}–${c.last_page})`}
              </option>
            ))}
          </select>
        </label>
      )}
      <button type="submit" disabled={busy}>
        {busy ? t("generate.running") : t("generate.submit")}
      </button>
      {result && (
        <p role="status">
          {t("generate.done")} <Link to={`/teacher/tasks/${result.task.id}`}>{result.task.title}</Link>
          {result.dropped_tests > 0 && ` ${t("generate.dropped", { n: result.dropped_tests })}`}
        </p>
      )}
      {error !== null && <ErrorText error={error} />}
    </form>
  );
}
