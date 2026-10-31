import { useTranslation } from "react-i18next";

import { ApiError, errorCode } from "../api/client";

/** Loading and error placeholders shared by the pages. */
export function Status({ loading, error }: { loading: boolean; error: unknown }) {
  const { t } = useTranslation();
  if (loading) return <p>{t("common.loading")}</p>;
  if (error instanceof ApiError && error.status === 403) {
    return <p role="alert">{t("errors.forbidden")}</p>;
  }
  if (error) return <ErrorText error={error} />;
  return null;
}

/** Shows a translated message for known API error codes, the raw code otherwise. */
export function ErrorText({ error }: { error: unknown }) {
  const { t } = useTranslation();
  const code = errorCode(error);
  const message =
    error instanceof ApiError && error.detail && typeof error.detail === "object"
      ? (error.detail as { message?: string }).message
      : undefined;
  const key = `apiErrors.${code}`;
  const text = code && t(key) !== key ? t(key) : t("errors.generic");
  return (
    <p role="alert">
      {text}
      {message ? ` (${message})` : ""}
    </p>
  );
}
