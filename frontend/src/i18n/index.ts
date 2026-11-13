import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import pl from "./pl.json";

/** A language picked on this device (first-time setup), else the browser's. */
function startLanguage(): string {
  try {
    const picked = localStorage.getItem("lang");
    if (picked === "pl" || picked === "en") return picked;
  } catch {
    // storage blocked: the browser's language
  }
  return navigator.language.startsWith("pl") ? "pl" : "en";
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, pl: { translation: pl } },
  lng: startLanguage(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export default i18n;
