import { useTranslation } from "react-i18next";

import { LANGUAGES, type Language, setLanguage } from "../i18n";

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  return (
    <label className="language">
      {t("nav.language")}{" "}
      <select
        value={i18n.language}
        onChange={(event) => setLanguage(event.target.value as Language)}
      >
        {LANGUAGES.map((language) => (
          <option key={language} value={language}>
            {t(`languages.${language}`)}
          </option>
        ))}
      </select>
    </label>
  );
}
