import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { apiSend } from "../../api/client";
import type { Rubric, RubricCriterion } from "../../api/types";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";

/** ФТ-13, ФТ-15: six criteria with three-level descriptors and the S weights. */
export function RubricPage() {
  const { courseId } = useParams();
  const rubric = useResource<Rubric>(`/api/courses/${courseId}/rubric`);
  if (!rubric.data) return <Status loading={rubric.loading} error={rubric.error} />;
  return <RubricForm key={courseId} courseId={Number(courseId)} initial={rubric.data} />;
}

function RubricForm({ courseId, initial }: { courseId: number; initial: Rubric }) {
  const { t } = useTranslation();
  const [rubric, setRubric] = useState(initial);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  const setCriterion = (index: number, change: Partial<RubricCriterion>) => {
    setSaved(false);
    setRubric({
      ...rubric,
      criteria: rubric.criteria.map((c, i) => (i === index ? { ...c, ...change } : c)),
    });
  };
  const setWeight = (key: "weight_f" | "weight_e" | "weight_a", value: number) => {
    setSaved(false);
    setRubric({ ...rubric, [key]: value });
  };
  const sum = rubric.weight_f + rubric.weight_e + rubric.weight_a;

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await apiSend("PUT", `/api/courses/${courseId}/rubric`, rubric);
      setSaved(true);
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <form className="card task-form" onSubmit={save}>
      <h1>{t("rubric.title")}</h1>
      <h2>{t("rubric.weights")}</h2>
      <p className="muted">S = wF·F + wE·E + wA·A</p>
      <div className="row">
        {(["weight_f", "weight_e", "weight_a"] as const).map((key) => (
          <label key={key}>
            {t(`rubric.${key}`)}
            <input
              type="number"
              step="0.0001"
              min={0}
              max={1}
              value={rubric[key]}
              onChange={(e) => setWeight(key, Number(e.target.value))}
            />
          </label>
        ))}
      </div>
      {Math.abs(sum - 1) > 0.001 && <p role="alert">{t("rubric.sumWarning", { sum: sum.toFixed(4) })}</p>}
      {(["F", "E", "A"] as const).map((key) => (
        <label key={key}>
          {t(`rubric.scale${key}`)}
          <textarea
            rows={2}
            value={rubric.component_scales[key]}
            onChange={(e) =>
              setRubric({ ...rubric, component_scales: { ...rubric.component_scales, [key]: e.target.value } })
            }
          />
        </label>
      ))}
      {rubric.criteria.map((criterion, i) => (
        <fieldset key={criterion.code} className="criterion">
          <legend>{criterion.name}</legend>
          {(["descriptor_low", "descriptor_mid", "descriptor_high"] as const).map((field) => (
            <label key={field}>
              {t(`rubric.${field}`)}
              <textarea rows={2} value={criterion[field]} onChange={(e) => setCriterion(i, { [field]: e.target.value })} />
            </label>
          ))}
        </fieldset>
      ))}
      <button type="submit">{t("common.save")}</button>
      {saved && <p role="status">{t("common.saved")}</p>}
      {error !== null && <ErrorText error={error} />}
    </form>
  );
}
