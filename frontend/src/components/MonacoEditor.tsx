// Loaded lazily: Monaco is large. It is bundled locally, not taken from a CDN (CSP 'self').
import Editor, { loader, type OnMount } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import EditorWorker from "monaco-editor/editor/editor.worker?worker";

import type { CodeEditorProps } from "./CodeEditor";

self.MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });

export default function MonacoEditor({ value, onChange, onPaste, label }: CodeEditorProps) {
  const handleMount: OnMount = (editor) => {
    editor.onDidPaste((event) => {
      const text = editor.getModel()?.getValueInRange(event.range) ?? "";
      onPaste(text.length, text.split("\n").length);
    });
  };
  return (
    <div aria-label={label}>
      <Editor
        height="420px"
        language="cpp"
        value={value}
        onChange={(next) => onChange(next ?? "")}
        onMount={handleMount}
        options={{ minimap: { enabled: false }, fontSize: 14, automaticLayout: true, tabSize: 4 }}
      />
    </div>
  );
}
