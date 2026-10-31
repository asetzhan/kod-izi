import { useTranslation } from "react-i18next";
import { Outlet, useNavigate } from "react-router";

import { useAuth } from "../auth/AuthContext";
import { LanguageSwitcher } from "./LanguageSwitcher";

export function Layout() {
  const { t } = useTranslation();
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await signOut();
    navigate("/login", { replace: true });
  };

  return (
    <>
      <header className="topbar">
        <strong>{t("app.title")}</strong>
        <div className="topbar-actions">
          <LanguageSwitcher />
          {user && (
            <>
              <span>{user.full_name}</span>
              <button type="button" onClick={handleLogout}>
                {t("nav.logout")}
              </button>
            </>
          )}
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </>
  );
}
