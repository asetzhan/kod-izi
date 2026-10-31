import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { apiSend, apiUpload } from "../../api/client";
import type { Binding, Course, Material, MaterialKind, TaskSummary } from "../../api/types";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";

/** ФТ-06: course books and lectures; ФТ-11: chapters bound as «бағалау негізі». */
export function MaterialsPage() {
  const { courseId } = useParams();
  const { t } = useTranslation();
  const materials = useResource<Material[]>(`/api/courses/${courseId}/materials`);
  const course = useResource<Course>(`/api/courses/${courseId}`);
  const tasks = useResource<TaskSummary[]>(`/api/tasks?course_id=${courseId}`);

  return (
    <>
      <section className="card">
        <h1>{t("materials.title")}</h1>
        <Status loading={materials.loading} error={materials.error} />
        {materials.data?.length === 0 && <p className="muted">{t("materials.none")}</p>}
        {materials.data?.map((m) => (
          <article key={m.id} className="material">
            <h2>
              {m.title} <small>({t(`materials.kinds.${m.kind}`)})</small>
            </h2>
            <ul>
              {m.versions.map((v) => (
                <li key={v.id}>
                  v{v.version} · {v.filename} · {t(`materials.status.${v.status}`)}
                  {v.pages ? ` · ${t("materials.pages", { count: v.pages })}` : ""}
                  {v.error && <span className="muted"> ({v.error})</span>}
                </li>
              ))}
            </ul>
            {m.versions.some((v) => v.status === "ready") && <DownloadButton materialId={m.id} />}
            <BindingForm material={m} course={course.data} tasks={tasks.data ?? []} />
          </article>
        ))}
      </section>
      <UploadForm courseId={Number(courseId)} onUploaded={materials.reload} />
    </>
  );
}

function UploadForm({ courseId, onUploaded }: { courseId: number; onUploaded: () => void }) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [kind, setKind] = useState<MaterialKind>("book");
  const [rights, setRights] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    setError(null);
    try {
      await apiUpload(`/api/courses/${courseId}/materials`, file, {
        title,
        author,
        kind,
        rights_confirmed: String(rights),
      });
      setTitle("");
      setFile(null);
      setRights(false);
      onUploaded();
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <form className="card inline-form" onSubmit={submit}>
      <h2>{t("materials.upload")}</h2>
      <p className="muted">{t("materials.hint")}</p>
      <label>
        {t("materials.file")}
        <input type="file" accept=".pdf,.docx,.epub,.pptx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <label>
        {t("materials.name")}
        <input required maxLength={300} value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        {t("materials.author")}
        <input maxLength={300} value={author} onChange={(e) => setAuthor(e.target.value)} />
      </label>
      <label>
        {t("materials.kind")}
        <select value={kind} onChange={(e) => setKind(e.target.value as MaterialKind)}>
          {(["book", "lecture", "problems"] as const).map((k) => (
            <option key={k} value={k}>
              {t(`materials.kinds.${k}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} />
        {t("materials.rights")}
      </label>
      <button type="submit" disabled={!file || !rights}>
        {t("materials.submit")}
      </button>
      {error !== null && <ErrorText error={error} />}
    </form>
  );
}

function BindingForm({
  material,
  course,
  tasks,
}: {
  material: Material;
  course: Course | undefined;
  tasks: TaskSummary[];
}) {
  const { t } = useTranslation();
  const bindings = useResource<Binding[]>(`/api/materials/${material.id}/bindings`);
  const [target, setTarget] = useState("");
  const [pageFrom, setPageFrom] = useState("");
  const [pageTo, setPageTo] = useState("");
  const [chapter, setChapter] = useState("");
  const [basis, setBasis] = useState(true);
  const [requirements, setRequirements] = useState("");
  const [error, setError] = useState<unknown>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const [kind, id] = target.split(":");
    try {
      await apiSend("POST", `/api/materials/${material.id}/bindings`, {
        topic_id: kind === "topic" ? Number(id) : null,
        task_id: kind === "task" ? Number(id) : null,
        assessment_id: null,
        chapter,
        page_from: pageFrom ? Number(pageFrom) : null,
        page_to: pageTo ? Number(pageTo) : null,
        is_assessment_basis: basis,
        requirements,
      });
      bindings.reload();
    } catch (caught) {
      setError(caught);
    }
  };

  const describe = (b: Binding) => {
    const topic = course?.topics.find((tp) => tp.id === b.topic_id);
    const task = tasks.find((x) => x.id === b.task_id);
    const what = topic ? `${topic.code} ${topic.title}` : task ? task.title : "—";
    const pages = b.page_from ? ` · ${b.page_from}–${b.page_to ?? b.page_from}` : "";
    return `${what}${b.chapter ? ` · ${b.chapter}` : ""}${pages}`;
  };

  return (
    <div>
      <ul>
        {bindings.data?.map((b) => (
          <li key={b.id}>
            {describe(b)} {b.is_assessment_basis && <strong>· {t("materials.basis")}</strong>}
          </li>
        ))}
      </ul>
      <form className="inline-form" onSubmit={submit}>
        <label>
          {t("materials.bindTo")}
          <select required value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">—</option>
            {course?.topics.map((tp) => (
              <option key={`topic:${tp.id}`} value={`topic:${tp.id}`}>
                {t("task.topic")}: {tp.code} {tp.title}
              </option>
            ))}
            {tasks.map((task) => (
              <option key={`task:${task.id}`} value={`task:${task.id}`}>
                {t("materials.task")}: {task.title}
              </option>
            ))}
          </select>
        </label>
        <div className="row">
          <label>
            {t("materials.chapter")}
            <input value={chapter} onChange={(e) => setChapter(e.target.value)} />
          </label>
          <label>
            {t("materials.pageFrom")}
            <input type="number" min={1} value={pageFrom} onChange={(e) => setPageFrom(e.target.value)} />
          </label>
          <label>
            {t("materials.pageTo")}
            <input type="number" min={1} value={pageTo} onChange={(e) => setPageTo(e.target.value)} />
          </label>
        </div>
        <label className="checkbox">
          <input type="checkbox" checked={basis} onChange={(e) => setBasis(e.target.checked)} />
          {t("materials.basis")}
        </label>
        <label>
          {t("materials.requirements")}
          <textarea rows={2} value={requirements} onChange={(e) => setRequirements(e.target.value)} />
        </label>
        <button type="submit">{t("materials.bind")}</button>
        {error !== null && <ErrorText error={error} />}
      </form>
    </div>
  );
}

/** Spec 14.1: the file is served by a signed link valid for a few minutes. */
function DownloadButton({ materialId }: { materialId: number }) {
  const { t } = useTranslation();
  const [error, setError] = useState<unknown>(null);
  const open = async () => {
    try {
      const link = await apiSend<{ url: string }>("POST", `/api/materials/${materialId}/link`);
      window.location.assign(link.url);
    } catch (caught) {
      setError(caught);
    }
  };
  return (
    <>
      <button type="button" className="link" onClick={open}>
        {t("materials.download")}
      </button>
      {error !== null && <ErrorText error={error} />}
    </>
  );
}
