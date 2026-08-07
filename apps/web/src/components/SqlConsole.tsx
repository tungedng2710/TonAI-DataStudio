import { AlertCircle, CheckCircle2, Download, LoaderCircle, Play, TerminalSquare } from "lucide-react";
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import type {
  BrowserSqlEngine,
  SqlExportFormat,
  SqlQueryResult,
} from "../duckdb-console";
import { queryForView, sqlViewsForConfigs } from "../sql-views";
import type { DatasetConfig } from "../types";

export function SqlConsole({
  namespace,
  dataset,
  revision,
  configs,
  onResult,
}: {
  namespace: string;
  dataset: string;
  revision: string;
  configs: DatasetConfig[];
  onResult: (result: SqlQueryResult, query: string) => void;
}) {
  const views = useMemo(() => sqlViewsForConfigs(configs), [configs]);
  const [query, setQuery] = useState(() => queryForView(views[0]?.name ?? "train"));
  const [hasResult, setHasResult] = useState(false);
  const [successfulQuery, setSuccessfulQuery] = useState("");
  const [status, setStatus] = useState("Ready to start");
  const [error, setError] = useState("");
  const [exportError, setExportError] = useState("");
  const [running, setRunning] = useState(false);
  const [exporting, setExporting] = useState<SqlExportFormat | null>(null);
  const engineRef = useRef<BrowserSqlEngine | null>(null);

  useEffect(() => {
    setQuery(queryForView(views[0]?.name ?? "train"));
    setHasResult(false);
    setSuccessfulQuery("");
    setError("");
    setExportError("");
    setStatus("Ready to start");
    const engine = engineRef.current;
    engineRef.current = null;
    if (engine) void engine.close();
  }, [revision, views]);

  useEffect(() => () => {
    if (engineRef.current) void engineRef.current.close();
  }, []);

  const runQuery = async () => {
    if (!query.trim() || running) return;
    setRunning(true);
    setError("");
    setExportError("");
    try {
      let engine = engineRef.current;
      if (!engine) {
        const { BrowserSqlEngine: Engine } = await import("../duckdb-console");
        engine = new Engine();
        engineRef.current = engine;
        try {
          await engine.initialize(
            views,
            async (path) => {
              const response = await fetch(api.blobUrl(namespace, dataset, revision, path, true), {
                credentials: "include",
              });
              if (!response.ok) {
                throw new Error(`Could not load ${path}: ${response.status} ${response.statusText}`);
              }
              return new Uint8Array(await response.arrayBuffer());
            },
            setStatus,
          );
        } catch (caught: unknown) {
          engineRef.current = null;
          await engine.close();
          throw caught;
        }
      }
      setStatus("Running query…");
      const nextResult = await engine.query(query);
      setHasResult(true);
      setSuccessfulQuery(query);
      onResult(nextResult, query);
      setStatus(
        `${nextResult.totalRows.toLocaleString()} row${nextResult.totalRows === 1 ? "" : "s"} · ${nextResult.elapsedMs.toFixed(0)} ms`,
      );
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The query could not be completed.");
      setStatus("Query failed");
      if (!engineRef.current) setStatus("DuckDB failed to start");
    } finally {
      setRunning(false);
    }
  };

  const downloadResult = async (format: SqlExportFormat) => {
    const engine = engineRef.current;
    if (!engine || !successfulQuery || exporting) return;
    setExporting(format);
    setExportError("");
    try {
      const exported = await engine.exportQuery(successfulQuery, format);
      const buffer = new ArrayBuffer(exported.bytes.byteLength);
      new Uint8Array(buffer).set(exported.bytes);
      const blob = new Blob([buffer], { type: exported.mediaType });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = exported.fileName;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught: unknown) {
      setExportError(caught instanceof Error ? caught.message : `Could not export ${format.toUpperCase()}.`);
    } finally {
      setExporting(null);
    }
  };

  const handleEditorKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void runQuery();
    }
  };

  return (
    <aside className="surface-panel flex min-h-[390px] min-w-0 flex-col overflow-hidden xl:sticky xl:top-20 xl:max-h-[calc(100vh-6rem)]" aria-label="SQL console">
      <div className="border-b border-slate-200 bg-slate-950 px-4 py-4 text-slate-100">
        <div className="flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-lg bg-indigo-500/20 text-indigo-300 ring-1 ring-indigo-400/25">
            <TerminalSquare className="size-4" />
          </span>
          <div>
            <h2 className="text-sm font-semibold">SQL console</h2>
            <p className="mt-0.5 text-[11px] text-slate-400">DuckDB WASM · browser only</p>
          </div>
        </div>
        <p className="mt-3 text-xs leading-5 text-slate-400">
          Type a query or select a view below. Source data stays in this browser tab.
        </p>
      </div>

      <div className="border-b border-slate-800 bg-slate-900 p-3">
        <textarea
          aria-label="SQL query"
          className="min-h-24 w-full resize-y rounded-lg border border-slate-700 bg-slate-950 p-3 font-mono text-xs leading-5 text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-indigo-500 focus:ring-3 focus:ring-indigo-500/15"
          value={query}
          spellCheck={false}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={handleEditorKeyDown}
        />
        <div className="mt-2 flex items-center justify-between gap-3">
          <span className="text-[10px] text-slate-500">⌘/Ctrl + Enter</span>
          <button className="button-primary min-h-8 px-3 text-xs" type="button" disabled={running || !query.trim()} onClick={() => void runQuery()}>
            {running ? <LoaderCircle className="size-3.5 animate-spin" /> : <Play className="size-3.5 fill-current" />}
            {running ? "Running" : "Run"}
          </button>
        </div>
      </div>

      <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
        <p className="text-[10px] font-bold tracking-[0.12em] text-slate-400 uppercase">Available views</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {views.map((view) => (
            <button
              className="rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-[11px] text-indigo-700 shadow-xs transition hover:border-indigo-300 hover:bg-indigo-50"
              type="button"
              title={`${view.config} / ${view.split}`}
              key={`${view.config}/${view.split}`}
              onClick={() => setQuery(queryForView(view.name))}
            >
              {view.name}
            </button>
          ))}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-2 text-[11px] text-slate-500">
          {running ? <LoaderCircle className="size-3 animate-spin text-indigo-500" /> : error ? <AlertCircle className="size-3 text-rose-500" /> : <CheckCircle2 className="size-3 text-emerald-500" />}
          <span className="truncate">{status}</span>
        </div>
        {error ? (
          <div className="m-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs leading-5 text-rose-700">{error}</div>
        ) : null}
        {hasResult ? (
          <div className="border-b border-slate-100 px-3 py-3">
            <p className="text-[10px] font-bold tracking-[0.12em] text-slate-400 uppercase">Download result</p>
            <div className="mt-2 grid grid-cols-3 gap-1.5">
              {(["csv", "json", "parquet"] as const).map((format) => (
                <button
                  className="button-secondary min-h-8 min-w-0 px-2 text-[10px] uppercase"
                  type="button"
                  disabled={exporting !== null}
                  key={format}
                  onClick={() => void downloadResult(format)}
                >
                  {exporting === format ? <LoaderCircle className="size-3 animate-spin" /> : <Download className="size-3" />}
                  {format}
                </button>
              ))}
            </div>
            {exportError ? <p className="mt-2 text-[11px] leading-4 text-rose-600">{exportError}</p> : null}
          </div>
        ) : null}
        {!error ? (
          <div className="grid flex-1 place-items-center p-6 text-center">
            <div>
              {hasResult ? <CheckCircle2 className="mx-auto size-7 text-emerald-400" /> : <TerminalSquare className="mx-auto size-7 text-slate-300" />}
              <p className="mt-2 text-xs font-medium text-slate-500">
                {hasResult ? "Results shown in the data preview" : "Run a query to update the data preview"}
              </p>
            </div>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
