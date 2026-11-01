import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { useResource } from "../../api/useResource";
import { Status } from "../../components/Status";
import { codeTimeline, type TraceEvent } from "../../workspace/replay";

interface SessionTrace {
  session_id: string;
  user_id: number;
  task_id: number;
  started_at: string;
  events: TraceEvent[];
}

const PLAY_MS = 600;

/** ФТ-28: replay how the code was written, on a time scale, with the activity stages (ФТ-26). */
export function ReplayPage() {
  const { sessionId } = useParams();
  const { t } = useTranslation();
  const trace = useResource<SessionTrace>(`/api/sessions/${sessionId}/trace`);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const total = trace.data?.events.length ?? 0;

  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      setIndex((i) => {
        if (i + 1 >= total) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, PLAY_MS);
    return () => clearInterval(timer);
  }, [playing, total]);

  if (!trace.data) return <Status loading={trace.loading} error={trace.error} />;
  const events = trace.data.events;
  const first = events[0];
  const current = events[Math.min(index, events.length - 1)];
  if (!first || !current) return <p className="card muted">{t("replay.empty")}</p>;
  const codes = codeTimeline(events);
  const start = new Date(first.server_ts).getTime();
  const minute = (e: TraceEvent) => ((new Date(e.server_ts).getTime() - start) / 60000).toFixed(1);

  return (
    <>
      <section className="card">
        <h1>{t("replay.title")}</h1>
        <div className="row">
          <button type="button" onClick={() => setPlaying(!playing)}>
            {playing ? t("replay.pause") : t("replay.play")}
          </button>
          <input
            type="range"
            aria-label={t("replay.position")}
            min={0}
            max={events.length - 1}
            value={index}
            onChange={(e) => setIndex(Number(e.target.value))}
          />
          <span>
            {t("replay.at", { minute: minute(current), n: index + 1, total: events.length })}
          </span>
        </div>
        <p>
          <strong>{t(`trace.kind.${current.kind}`, { defaultValue: current.kind })}</strong>
          {current.stage && <> · {t(`stage.${current.stage}`)}</>}
          {current.flagged && <span className="flag"> · {t("replay.flagged")}</span>}
        </p>
        <pre className="io code-replay" aria-label={t("replay.code")}>
          {codes[index]}
        </pre>
      </section>
      <section className="card">
        <h2>{t("replay.events")}</h2>
        <ol>
          {events.map((e, i) => (
            <li key={e.id} className={i === index ? "me" : undefined}>
              <button type="button" className="link" onClick={() => setIndex(i)}>
                {minute(e)}′ {t(`trace.kind.${e.kind}`, { defaultValue: e.kind })}
              </button>
              {e.stage && <span className="muted"> · {t(`stage.${e.stage}`)}</span>}
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
