import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { apiSend } from "../../api/client";
import type { OlympiadOverview, OlympiadSettings } from "../../api/olympiad";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";

/** Coach cabinet: olympiad courses and their contests, settings of ОТ-04 and ОТ-05. */
export function CoachHomePage() {
  const { t } = useTranslation();
  const overview = useResource<OlympiadOverview>("/api/olympiad");

  return (
    <>
      <section className="card">
        <h1>{t("cabinet.coach")}</h1>
        <Status loading={overview.loading} error={overview.error} />
        <ul>
          {overview.data?.courses.map((c) => (
            <li key={c.id}>
              {c.title}: <Link to={`/coach/courses/${c.id}/contests`}>{t("contest.list")}</Link>
            </li>
          ))}
        </ul>
        <p className="muted">{t("olympiad.coachTasksHint")}</p>
      </section>
      <SettingsForm />
    </>
  );
}

function SettingsForm() {
  const stored = useResource<OlympiadSettings>("/api/settings/olympiad");
  if (!stored.data) return <Status loading={stored.loading} error={stored.error} />;
  return <SettingsEditor initial={stored.data} />;
}

function SettingsEditor({ initial }: { initial: OlympiadSettings }) {
  const { t } = useTranslation();
  const [form, setForm] = useState<OlympiadSettings>(initial);
  const [topics, setTopics] = useState(initial.unlock_topics.join(", "));
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const number = (key: keyof OlympiadSettings) => (
    <label key={key}>
      {t(`olympiad.settings.${key}`)}
      <input
        type="number"
        value={form[key] as number}
        onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })}
      />
    </label>
  );

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSaved(false);
    try {
      const unlock_topics = topics
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      setForm(await apiSend<OlympiadSettings>("PUT", "/api/settings/olympiad", { ...form, unlock_topics }));
      setSaved(true);
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <section className="card">
      <h2>{t("olympiad.settings.title")}</h2>
      <form className="inline-form" onSubmit={save}>
        <label>
          {t("olympiad.settings.unlock_topics")}
          <input value={topics} onChange={(e) => setTopics(e.target.value)} />
        </label>
        {number("recommend_min")}
        {number("recommend_max")}
        {number("start_rating")}
        {number("editorial_after_minutes")}
        {number("hint_step_minutes")}
        <button type="submit">{t("common.save")}</button>
        {saved && <p>{t("common.saved")}</p>}
      </form>
      {error !== null && <ErrorText error={error} />}
    </section>
  );
}
