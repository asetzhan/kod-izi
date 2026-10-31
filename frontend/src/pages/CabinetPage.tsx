import { useTranslation } from "react-i18next";

import type { Role } from "../api/client";

/** Empty cabinet for each role; filled from stage 1 on. */
export function CabinetPage({ role }: { role: Role }) {
  const { t } = useTranslation();
  return (
    <section className="card">
      <h1>{t(`cabinet.${role}`)}</h1>
      <p>{t("cabinet.empty")}</p>
    </section>
  );
}
