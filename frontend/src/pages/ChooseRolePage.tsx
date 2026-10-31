import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ROLE_HOME, useAuth } from "../auth/AuthContext";

export function ChooseRolePage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  return (
    <section className="card">
      <h1>{t("chooseRole.title")}</h1>
      <ul>
        {user?.roles.map((role) => (
          <li key={role}>
            <Link to={ROLE_HOME[role]}>{t(`roles.${role}`)}</Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
