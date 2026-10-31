import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { apiGet, apiSend } from "../../api/client";
import type { ComponentEntry, ComponentSummary, EntryVersion } from "../../api/types";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";

/**
 * ФТ-07: the five components of the model around its core, as in the dissertation's
 * diagram. Clicking a component opens its entries (spec 6).
 */
export function ModelPanelPage() {
  const { courseId } = useParams();
  const { t } = useTranslation();
  const overview = useResource<ComponentSummary[]>(`/api/courses/${courseId}/components`);
  const [open, setOpen] = useState<number | null>(null);

  if (!overview.data) return <Status loading={overview.loading} error={overview.error} />;
  const box = (n: number) => {
    const c = overview.data!.find((x) => x.component === n)!;
    return (
      <button
        type="button"
        className={`model-box c${n}${open === n ? " active" : ""}`}
        aria-pressed={open === n}
        onClick={() => setOpen(n)}
      >
        <strong>
          {n}. {t(`panel.components.${n}`)}
        </strong>
        <small>
          {t("panel.entries", { count: c.entries })}
          {c.suggestions > 0 && ` · ${t("panel.suggestions", { count: c.suggestions })}`}
          {!c.auto_enabled && ` · ${t("panel.manualOnly")}`}
        </small>
      </button>
    );
  };

  return (
    <>
      <section className="card">
        <h1>{t("panel.title")}</h1>
        <div className="model-diagram" role="group" aria-label={t("panel.title")}>
          {box(1)}
          {box(2)}
          {box(3)}
          <div className="model-core">{t("panel.core")}</div>
          {box(4)}
          {box(5)}
        </div>
      </section>
      {open !== null && (
        <ComponentView
          key={open}
          courseId={Number(courseId)}
          summary={overview.data.find((c) => c.component === open)!}
          onChanged={overview.reload}
        />
      )}
    </>
  );
}

function ComponentView({
  courseId,
  summary,
  onChanged,
}: {
  courseId: number;
  summary: ComponentSummary;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const n = summary.component;
  const entries = useResource<ComponentEntry[]>(`/api/courses/${courseId}/components/${n}/entries`);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const act = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      entries.reload();
      onChanged();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <h2>
        {n}. {t(`panel.components.${n}`)}
      </h2>
      <p className="muted">{t(`panel.hints.${n}`)}</p>
      <div className="row">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={summary.auto_enabled}
            disabled={busy}
            onChange={(e) =>
              act(() =>
                apiSend("PUT", `/api/courses/${courseId}/components/${n}/settings`, {
                  auto_enabled: e.target.checked,
                }),
              )
            }
          />
          {t("panel.autoFill")}
        </label>
        {(n === 1 || n === 2) && (
          <button
            type="button"
            disabled={busy || !summary.auto_enabled}
            onClick={() => act(() => apiSend("POST", `/api/courses/${courseId}/components/${n}/generate`))}
          >
            {t("panel.generate")}
          </button>
        )}
      </div>
      {error !== null && <ErrorText error={error} />}
      <Status loading={entries.loading} error={entries.error} />
      {entries.data?.length === 0 && <p className="muted">{t("panel.empty")}</p>}
      {entries.data?.map((entry) => (
        <EntryCard key={entry.id} entry={entry} readOnly={n === 4} act={act} busy={busy} />
      ))}
    </section>
  );
}

function EntryCard({
  entry,
  readOnly,
  act,
  busy,
}: {
  entry: ComponentEntry;
  readOnly: boolean;
  act: (action: () => Promise<unknown>) => Promise<void>;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<string | null>(null);
  const [versions, setVersions] = useState<EntryVersion[] | null>(null);
  const [invalid, setInvalid] = useState(false);

  const save = () => {
    try {
      const value: unknown = JSON.parse(draft ?? "null");
      setInvalid(false);
      void act(async () => {
        await apiSend("PUT", `/api/entries/${entry.id}`, { value });
        setDraft(null);
      });
    } catch {
      setInvalid(true);
    }
  };

  return (
    <article className="entry">
      <header className="row">
        <strong>
          {t(`panel.subjects.${entry.subject_type}`)} #{entry.subject_id} · {entry.key}
        </strong>
        <span className={`badge source-${entry.source}`}>{t(`panel.source.${entry.source}`)}</span>
      </header>
      {draft === null ? (
        <pre className="io">{JSON.stringify(entry.value, null, 2)}</pre>
      ) : (
        <label>
          {t("panel.editJson")}
          <textarea className="code" rows={10} value={draft} onChange={(e) => setDraft(e.target.value)} />
        </label>
      )}
      {invalid && <p role="alert">{t("panel.invalidJson")}</p>}
      {entry.suggestion !== null && entry.suggestion !== undefined && (
        <div className="suggestion">
          <p>{t("panel.suggestionText")}</p>
          <pre className="io">{JSON.stringify(entry.suggestion, null, 2)}</pre>
          <div className="row">
            <button type="button" disabled={busy} onClick={() => act(() => apiSend("POST", `/api/entries/${entry.id}/suggestion/accept`))}>
              {t("panel.accept")}
            </button>
            <button type="button" disabled={busy} onClick={() => act(() => apiSend("POST", `/api/entries/${entry.id}/suggestion/reject`))}>
              {t("panel.reject")}
            </button>
          </div>
        </div>
      )}
      <div className="row">
        {!readOnly &&
          (draft === null ? (
            <button type="button" onClick={() => setDraft(JSON.stringify(entry.value, null, 2))}>
              {t("panel.edit")}
            </button>
          ) : (
            <>
              <button type="button" disabled={busy} onClick={save}>
                {t("common.save")}
              </button>
              <button type="button" onClick={() => setDraft(null)}>
                {t("panel.cancel")}
              </button>
            </>
          ))}
        <button
          type="button"
          onClick={async () => setVersions(versions ? null : await apiGet<EntryVersion[]>(`/api/entries/${entry.id}/versions`))}
        >
          {t("panel.history", { count: entry.versions })}
        </button>
      </div>
      {versions && (
        <ol className="versions">
          {versions.map((v) => (
            <li key={v.version}>
              v{v.version} · {new Date(v.created_at).toLocaleString()} · {t(`panel.source.${v.source}`)}
              {v.note && ` · ${v.note}`}{" "}
              {!readOnly && (
                <button
                  type="button"
                  className="link"
                  disabled={busy}
                  onClick={() =>
                    act(async () => {
                      await apiSend("POST", `/api/entries/${entry.id}/revert`, { version: v.version });
                      setVersions(null);
                    })
                  }
                >
                  {t("panel.restore")}
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}
