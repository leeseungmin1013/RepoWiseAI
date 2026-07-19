"use client";

import Editor, { type OnMount } from "@monaco-editor/react";
import { Braces, GitFork, LoaderCircle } from "lucide-react";
import type { editor } from "monaco-editor";
import { useEffect, useRef, useState } from "react";

import type { CodeSelection, GraphData, SourceFile, SymbolRecord } from "@/lib/api";

import { DependencyGraph } from "./DependencyGraph";

type Props = {
  file: SourceFile | null;
  symbols: SymbolRecord[];
  graph: GraphData | null;
  loading: boolean;
  view: "code" | "graph";
  highlight: CodeHighlight | null;
  onViewChange: (view: "code" | "graph") => void;
  onOpenFile: (fileId: string) => void;
  onSelectionChange: (selection: CodeSelection | null) => void;
};

export type CodeHighlight = {
  fileId: string;
  startLine: number;
  endLine: number;
};

function editorLanguage(language: string) {
  if (language === "tsx" || language === "jsx") return "typescript";
  if (language === "yaml") return "yaml";
  return language;
}

export function CodePanel({
  file,
  symbols,
  graph,
  loading,
  view,
  highlight,
  onViewChange,
  onOpenFile,
  onSelectionChange,
}: Props) {
  const [editorInstance, setEditorInstance] =
    useState<editor.IStandaloneCodeEditor | null>(null);
  const decorationIds = useRef<string[]>([]);

  const handleMount: OnMount = (mountedEditor) => {
    decorationIds.current = [];
    setEditorInstance(mountedEditor);
    if (file && highlight?.fileId === file.id) {
      window.requestAnimationFrame(() => {
        decorationIds.current = applyCitationHighlight(
          mountedEditor,
          highlight,
          decorationIds.current,
        );
      });
    }
  };

  useEffect(() => {
    if (!editorInstance) return;
    const disposable = editorInstance.onDidChangeCursorSelection((event) => {
      if (!file || event.selection.isEmpty()) {
        onSelectionChange(null);
        return;
      }
      onSelectionChange({
        file_id: file.id,
        start_line: event.selection.startLineNumber,
        end_line: event.selection.endLineNumber,
      });
    });
    return () => disposable.dispose();
  }, [editorInstance, file, onSelectionChange]);

  useEffect(() => {
    if (!editorInstance) return;
    const active = file && highlight?.fileId === file.id ? highlight : null;
    const frame = window.requestAnimationFrame(() => {
      const modelPath = editorInstance.getModel()?.uri.path.replace(/^\//, "");
      if (file && modelPath !== file.path) return;
      decorationIds.current = applyCitationHighlight(
        editorInstance,
        active,
        decorationIds.current,
      );
    });
    return () => window.cancelAnimationFrame(frame);
  }, [editorInstance, file, highlight]);

  return (
    <section className="code-panel">
      <div className="panel-toolbar code-toolbar">
        <div className="file-breadcrumb">
          <Braces aria-hidden size={16} />
          <span title={file?.path}>{file?.path ?? "코드 탐색기"}</span>
          {file ? <small>{file.line_count.toLocaleString()} lines</small> : null}
        </div>
        <div className="view-tabs" aria-label="Code workspace view">
          <button
            className={view === "code" ? "is-active" : ""}
            onClick={() => onViewChange("code")}
            type="button"
          >
            <Braces aria-hidden size={14} /> 코드
          </button>
          <button
            className={view === "graph" ? "is-active" : ""}
            onClick={() => onViewChange("graph")}
            type="button"
          >
            <GitFork aria-hidden size={14} /> 관계
          </button>
        </div>
      </div>

      <div className="code-surface">
        {loading ? (
          <div className="panel-empty">
            <LoaderCircle className="spin" aria-hidden size={22} />
            <span>파일을 불러오는 중</span>
          </div>
        ) : view === "graph" ? (
          <DependencyGraph graph={graph} onOpenFile={onOpenFile} />
        ) : file ? (
          <Editor
            key={file.id}
            height="100%"
            language={editorLanguage(file.language)}
            path={file.path}
            value={file.content}
            theme="vs-light"
            onMount={handleMount}
            options={{
              readOnly: true,
              automaticLayout: true,
              minimap: { enabled: false },
              fontSize: 13,
              lineHeight: 21,
              padding: { top: 14, bottom: 14 },
              scrollBeyondLastLine: false,
              renderLineHighlight: "line",
              wordWrap: "off",
              smoothScrolling: true,
            }}
          />
        ) : (
          <div className="panel-empty">
            <Braces aria-hidden size={24} />
            <span>분석된 파일을 선택하세요.</span>
          </div>
        )}
      </div>

      {view === "code" && file ? (
        <footer className="symbol-strip">
          <span>{file.language}</span>
          <span>{symbols.length} symbols</span>
          {symbols.slice(0, 3).map((symbol) => (
            <button key={symbol.id} type="button" title={symbol.signature ?? symbol.display_name}>
              {symbol.display_name}
            </button>
          ))}
        </footer>
      ) : null}
    </section>
  );
}

function applyCitationHighlight(
  editorInstance: editor.IStandaloneCodeEditor,
  highlight: CodeHighlight | null,
  previousIds: string[],
) {
  const model = editorInstance.getModel();
  if (!model || !highlight || model.getLineCount() < highlight.startLine) {
    return editorInstance.deltaDecorations(previousIds, []);
  }
  const endLine = Math.min(highlight.endLine, model.getLineCount());
  const nextIds = editorInstance.deltaDecorations(previousIds, [
    {
      range: {
        startLineNumber: highlight.startLine,
        startColumn: 1,
        endLineNumber: endLine,
        endColumn: model.getLineMaxColumn(endLine),
      },
      options: {
        isWholeLine: true,
        className: "citation-line-highlight",
        linesDecorationsClassName: "citation-line-marker",
      },
    },
  ]);
  editorInstance.revealLinesInCenter(highlight.startLine, endLine);
  return nextIds;
}
