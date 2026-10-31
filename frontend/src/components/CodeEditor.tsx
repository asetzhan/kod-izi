import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";

export interface CodeEditorProps {
  value: string;
  onChange: (code: string) => void;
  /** ФТ-29: size of every paste goes to the digital trace. */
  onPaste: (length: number, lines: number) => void;
  label: string;
}

const MonacoEditor = lazy(() => import("./MonacoEditor"));

/** C++ editor (ФТ-24). */
export function CodeEditor(props: CodeEditorProps) {
  const { t } = useTranslation();
  return (
    <Suspense fallback={<p>{t("common.loading")}</p>}>
      <MonacoEditor {...props} />
    </Suspense>
  );
}
