import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import kk from "./kk.json";
import ru from "./ru.json";

export const LANGUAGES = ["kk", "ru"] as const;
export type Language = (typeof LANGUAGES)[number];

const STORAGE_KEY = "kod-izi.lang";

function isLanguage(value: unknown): value is Language {
  return LANGUAGES.includes(value as Language);
}

function storedLanguage(): Language {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (isLanguage(value)) return value;
  } catch {
    // Storage can be unavailable (private mode); fall back to Kazakh.
  }
  return "kk";
}

void i18n.use(initReactI18next).init({
  resources: { kk: { translation: kk }, ru: { translation: ru } },
  lng: storedLanguage(),
  fallbackLng: "kk",
  interpolation: { escapeValue: false },
});

export function setLanguage(language: Language): void {
  void i18n.changeLanguage(language);
  document.documentElement.lang = language;
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // Not critical: the choice just will not survive a reload.
  }
}

export default i18n;
