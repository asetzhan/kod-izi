import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiSend } from "../../api/client";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";

interface KnowledgeMap {
  topics: { tag: string; bank: number; tried: number; solved: number; external: number; mastery: number }[];
  rating: {
    internal: { at: string; rating: number }[];
    codeforces: { at: string; rating: number; contest: string }[];
  };
}

interface External {
  accounts: {
    platform: string;
    handle: string;
    rating: number | null;
    max_rating: number | null;
    sync_status: string;
    sync_error: string | null;
    last_sync_at: string | null;
  }[];
  solves: {
    id: number;
    platform: string;
    title: string;
    url: string;
    rating: number | null;
    source: string;
    verified: boolean;
  }[];
}

const PLATFORMS = ["codeforces", "stepik", "cses", "atcoder", "acmp"] as const;

/** A small line of ratings over time, drawn without a chart library. */
function RatingLine({ points, label }: { points: { at: string; rating: number }[]; label: string }) {
  if (points.length === 0) return null;
  const width = 320;
  const height = 80;
  const values = points.map((p) => p.rating);
  const low = Math.min(...values) - 50;
  const high = Math.max(...values) + 50;
  const x = (i: number) => (points.length === 1 ? width / 2 : (i / (points.length - 1)) * width);
  const y = (v: number) => height - ((v - low) / (high - low)) * height;
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.rating).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  return (
    <figure>
      <svg width={width} height={height} role="img" aria-label={label}>
        <path d={path} fill="none" stroke="currentColor" strokeWidth={2} />
      </svg>
      <figcaption>
        {label}: {last?.rating}
      </figcaption>
    </figure>
  );
}

/** ОТ-09 knowledge map and ОТ-08 external platforms. */
export function KnowledgeMapPage() {
  const { t } = useTranslation();
  const map = useResource<KnowledgeMap>("/api/my/knowledge-map");

  return (
    <>
      <section className="card">
        <h1>{t("knowledge.title")}</h1>
        <Status loading={map.loading} error={map.error} />
        {map.data && (
          <>
            <table aria-label={t("knowledge.topics")}>
              <thead>
                <tr>
                  <th>{t("olympiad.tags")}</th>
                  <th>{t("knowledge.solved")}</th>
                  <th>{t("knowledge.external")}</th>
                  <th>{t("knowledge.mastery")}</th>
                </tr>
              </thead>
              <tbody>
                {map.data.topics.map((row) => (
                  <tr key={row.tag}>
                    <td>{row.tag}</td>
                    <td>
                      {row.solved}/{row.bank}
                    </td>
                    <td>{row.external}</td>
                    <td>
                      <meter min={0} max={1} value={row.mastery} aria-label={row.tag} />{" "}
                      {Math.round(row.mastery * 100)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h2>{t("knowledge.rating")}</h2>
            <RatingLine points={map.data.rating.internal} label={t("knowledge.internalRating")} />
            <RatingLine points={map.data.rating.codeforces} label="Codeforces" />
          </>
        )}
      </section>
      <ExternalAccounts onChange={map.reload} />
    </>
  );
}

function ExternalAccounts({ onChange }: { onChange: () => void }) {
  const { t } = useTranslation();
  const external = useResource<External>("/api/my/external");
  const [handle, setHandle] = useState("");
  const [consent, setConsent] = useState(false);
  const [platform, setPlatform] = useState<(typeof PLATFORMS)[number]>("cses");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<unknown>(null);

  const act = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      external.reload();
      onChange();
    } catch (caught) {
      setError(caught);
    }
  };

  const link = (event: FormEvent) => {
    event.preventDefault();
    void act(() => apiSend("POST", "/api/my/external/codeforces", { handle, consent }));
  };
  const mark = (event: FormEvent) => {
    event.preventDefault();
    void act(async () => {
      await apiSend("POST", "/api/my/external/solves", { platform, url, title });
      setUrl("");
      setTitle("");
    });
  };

  const account = external.data?.accounts.find((a) => a.platform === "codeforces");
  return (
    <section className="card">
      <h2>{t("external.title")}</h2>
      {account ? (
        <div>
          <p>
            Codeforces: <strong>{account.handle}</strong>
            {account.rating !== null && ` · ${t("external.rating", { rating: account.rating, max: account.max_rating })}`}
          </p>
          <p className="muted">
            {t(`external.status.${account.sync_status}`)}
            {account.sync_error && `: ${account.sync_error}`}
          </p>
          <div className="row">
            <button type="button" onClick={() => void act(() => apiSend("POST", "/api/my/external/codeforces/sync"))}>
              {t("external.sync")}
            </button>
            <button type="button" onClick={() => void act(() => apiSend("DELETE", "/api/my/external/codeforces"))}>
              {t("external.unlink")}
            </button>
          </div>
        </div>
      ) : (
        <form className="inline-form" onSubmit={link}>
          <label>
            {t("external.handle")}
            <input required minLength={3} maxLength={24} value={handle} onChange={(e) => setHandle(e.target.value)} />
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            {t("external.consent")}
          </label>
          <button type="submit" disabled={!consent}>
            {t("external.link")}
          </button>
        </form>
      )}
      <h3>{t("external.markTitle")}</h3>
      <form className="inline-form" onSubmit={mark}>
        <label>
          {t("external.platform")}
          <select value={platform} onChange={(e) => setPlatform(e.target.value as (typeof PLATFORMS)[number])}>
            {PLATFORMS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("external.url")}
          <input required type="url" maxLength={500} value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label>
          {t("external.problemTitle")}
          <input maxLength={300} value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <button type="submit">{t("external.mark")}</button>
      </form>
      {error !== null && <ErrorText error={error} />}
      <ul aria-label={t("external.solves")}>
        {external.data?.solves.map((s) => (
          <li key={s.id}>
            {s.platform}:{" "}
            <a href={s.url} target="_blank" rel="noreferrer">
              {s.title || s.url}
            </a>
            {s.rating !== null && ` (${s.rating})`}
            {!s.verified && <span className="muted"> · {t("external.unverified")}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
