import { useVirtualizer } from "@tanstack/react-virtual";
import { Check, Copy, Expand, ImageIcon, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { FieldSchema } from "../types";

interface EmbeddedImageReference {
  _type: "image";
  row: number;
  column: string;
  path: string | null;
  size: number | null;
}

interface PreviewedImage {
  url: string;
  alt: string;
}

function isEmbeddedImageReference(value: unknown): value is EmbeddedImageReference {
  return (
    typeof value === "object"
    && value !== null
    && "_type" in value
    && value._type === "image"
    && "row" in value
    && typeof value.row === "number"
    && "column" in value
    && typeof value.column === "string"
  );
}

function isImageReference(value: unknown): value is { _type: "image"; path: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    "_type" in value &&
    value._type === "image" &&
    "path" in value &&
    typeof value.path === "string"
  );
}

function formatValue(value: unknown, spacing?: number): string {
  try {
    return JSON.stringify(
      value,
      (_key, item: unknown) => (typeof item === "bigint" ? item.toString() : item),
      spacing,
    );
  } catch {
    return String(value);
  }
}

function Cell({
  value,
  namespace,
  dataset,
  revision,
  config,
  split,
  inspect,
  previewImage,
}: {
  value: unknown;
  namespace: string;
  dataset: string;
  revision: string;
  config: string;
  split: string;
  inspect: () => void;
  previewImage: (image: PreviewedImage) => void;
}) {
  if (value === null || value === undefined) {
    return <span className="font-mono text-xs text-slate-300">null</span>;
  }
  if (isEmbeddedImageReference(value)) {
    const thumbnailUrl = api.viewerMediaUrl(
      namespace,
      dataset,
      config,
      split,
      value.row,
      value.column,
      revision,
    );
    const fullImageUrl = api.viewerMediaUrl(
      namespace,
      dataset,
      config,
      split,
      value.row,
      value.column,
      revision,
      false,
    );
    const imageAlt = value.path || `Image at row ${value.row + 1}`;
    return (
      <button
        className="flex min-w-0 max-w-full items-center gap-2 overflow-hidden font-medium text-indigo-700 hover:text-indigo-500"
        type="button"
        onClick={() => previewImage({ url: fullImageUrl, alt: imageAlt })}
      >
        <span className="relative grid size-10 shrink-0 place-items-center overflow-hidden rounded-lg bg-indigo-50 text-indigo-500 ring-1 ring-indigo-100">
          <ImageIcon className="absolute size-4" />
          <img
            className="relative size-full object-cover"
            src={thumbnailUrl}
            alt={imageAlt}
            loading="lazy"
            onError={(event) => {
              event.currentTarget.style.display = "none";
            }}
          />
        </span>
        <span className="min-w-0 flex-1 truncate">
          {value.path || `Image · row ${value.row + 1}`}
        </span>
      </button>
    );
  }
  if (isImageReference(value)) {
    return (
      <a
        className="flex min-w-0 max-w-full items-center gap-2 overflow-hidden font-medium text-indigo-700 hover:text-indigo-500"
        href={api.blobUrl(namespace, dataset, revision, value.path, true)}
        target="_blank"
        rel="noreferrer"
      >
        <span className="relative grid size-8 shrink-0 place-items-center overflow-hidden rounded-lg bg-indigo-50 text-indigo-500 ring-1 ring-indigo-100">
          <ImageIcon className="absolute size-4" />
          <img
            className="relative size-full object-cover"
            src={api.blobUrl(namespace, dataset, revision, value.path, true)}
            alt="Dataset preview"
            loading="lazy"
            onError={(event) => {
              event.currentTarget.style.display = "none";
            }}
          />
        </span>
        <span className="min-w-0 flex-1 truncate">{value.path}</span>
      </a>
    );
  }
  if (typeof value === "string") {
    return value.length > 80 ? (
      <button
        className="group flex w-full min-w-0 max-w-full items-center gap-2 overflow-hidden text-left text-slate-700 hover:text-indigo-700"
        type="button"
        onClick={inspect}
      >
        <span className="block min-w-0 flex-1 truncate">{value}</span>
        <Expand className="size-3.5 shrink-0 opacity-0 transition group-hover:opacity-100" />
      </button>
    ) : (
      <span className="block max-w-full truncate" title={value}>{value}</span>
    );
  }
  if (typeof value === "object") {
    return (
      <button
        className="group flex w-full min-w-0 max-w-full items-center gap-2 overflow-hidden text-left font-mono text-xs text-violet-700 hover:text-violet-500"
        type="button"
        onClick={inspect}
      >
        <span className="block min-w-0 flex-1 truncate">{formatValue(value)}</span>
        <Expand className="size-3.5 shrink-0 opacity-50 transition group-hover:opacity-100" />
      </button>
    );
  }
  if (typeof value === "boolean") {
    return <span className="font-mono text-violet-700">{value ? "true" : "false"}</span>;
  }
  if (typeof value === "number" || typeof value === "bigint") {
    return <span className="font-mono text-blue-700">{value.toString()}</span>;
  }
  if (typeof value === "symbol") return <span>{value.description ?? "symbol"}</span>;
  if (typeof value === "function") return <span className="text-slate-400">[function]</span>;
  return <span className="text-slate-400">[unsupported value]</span>;
}

function ImageLightbox({
  image,
  close,
}: {
  image: PreviewedImage;
  close: () => void;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [close]);

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-slate-950/80 p-4 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <section
        className="relative flex max-h-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-slate-950 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label="Image preview"
      >
        <button
          className="absolute top-3 right-3 z-10 grid size-9 place-items-center rounded-xl bg-slate-950/70 text-white ring-1 ring-white/15 transition hover:bg-slate-800"
          type="button"
          onClick={close}
          aria-label="Close image preview"
        >
          <X className="size-4" />
        </button>
        <img
          className="max-h-[calc(100vh-2rem)] max-w-full object-contain"
          src={image.url}
          alt={image.alt}
        />
      </section>
    </div>
  );
}

interface InspectedCell {
  column: string;
  value: unknown;
}

function CellInspector({ cell, close }: { cell: InspectedCell; close: () => void }) {
  const formatted = typeof cell.value === "string" ? cell.value : formatValue(cell.value, 2);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [close]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(formatted);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1_200);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/55 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <section
        className="flex h-full w-full max-w-2xl flex-col border-l border-white/10 bg-slate-950 text-slate-100 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cell-inspector-title"
      >
        <header className="flex items-start justify-between gap-4 border-b border-white/10 px-6 py-5">
          <div>
            <p className="text-[10px] font-bold tracking-[0.2em] text-cyan-300 uppercase">Cell inspector</p>
            <h2 id="cell-inspector-title" className="mt-1 font-semibold text-white">{cell.column}</h2>
          </div>
          <div className="flex gap-2">
            <button className="grid size-9 place-items-center rounded-xl border border-white/10 text-slate-300 transition hover:bg-white/10 hover:text-white" type="button" onClick={() => void copy()} aria-label="Copy cell value">
              {copied ? <Check className="size-4 text-emerald-300" /> : <Copy className="size-4" />}
            </button>
            <button className="grid size-9 place-items-center rounded-xl border border-white/10 text-slate-300 transition hover:bg-white/10 hover:text-white" type="button" onClick={close} aria-label="Close cell inspector">
              <X className="size-4" />
            </button>
          </div>
        </header>
        <pre className="min-h-0 flex-1 overflow-auto p-6 font-mono text-xs leading-6 whitespace-pre-wrap text-slate-200">{formatted}</pre>
      </section>
    </div>
  );
}

interface DataTableProps {
  rows: Record<string, unknown>[];
  schema: FieldSchema[];
  namespace: string;
  dataset: string;
  revision: string;
  config: string;
  split: string;
  rowOffset?: number;
  rowIndices?: number[];
}

export function DataTable({
  rows,
  schema,
  namespace,
  dataset,
  revision,
  config,
  split,
  rowOffset = 0,
  rowIndices,
}: DataTableProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState<number | null>(null);
  const [copyError, setCopyError] = useState(false);
  const [inspected, setInspected] = useState<InspectedCell | null>(null);
  const [previewedImage, setPreviewedImage] = useState<PreviewedImage | null>(null);
  const columns = schema.length ? schema.map((field) => field.name) : Object.keys(rows[0] ?? {});
  const gridTemplateColumns = `64px repeat(${columns.length}, minmax(210px, 1fr))`;
  const minimumTableWidth = 64 + columns.length * 210;
  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => viewportRef.current,
    estimateSize: () => 52,
    overscan: 8,
  });

  const copyRow = async (index: number) => {
    try {
      await navigator.clipboard.writeText(formatValue(rows[index], 2));
      setCopyError(false);
      setCopied(index);
      window.setTimeout(() => setCopied(null), 1_200);
    } catch {
      setCopyError(true);
      window.setTimeout(() => setCopyError(false), 2_000);
    }
  };

  return (
    <>
      <div className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm shadow-slate-900/5">
        {copyError ? (
          <div className="absolute top-3 right-3 z-30 rounded-lg bg-rose-600 px-3 py-2 text-xs font-semibold text-white shadow-lg">
            Clipboard access was blocked
          </div>
        ) : null}
        <div className="overflow-x-auto">
          <div className="w-full" style={{ minWidth: minimumTableWidth }}>
            <div
              className="overflow-y-auto border-b border-slate-200 bg-slate-50/90"
              style={{ scrollbarGutter: "stable" }}
            >
              <div
                className="grid w-full text-xs font-semibold text-slate-500"
                style={{ gridTemplateColumns }}
              >
                <div className="px-4 py-3">#</div>
                {columns.map((column) => {
                  const field = schema.find((item) => item.name === column);
                  return (
                    <div className="border-l border-slate-200 px-4 py-3" key={column}>
                      <span className="text-slate-900">{column}</span>
                      <span className="ml-2 rounded-md bg-indigo-50 px-1.5 py-0.5 font-mono text-[10px] font-normal text-indigo-600">
                        {field?.type ?? "unknown"}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div
              ref={viewportRef}
              className="h-[540px] overflow-x-hidden overflow-y-auto"
              style={{ scrollbarGutter: "stable" }}
            >
              <div
                className="relative w-full"
                style={{ height: rowVirtualizer.getTotalSize() }}
              >
                {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                  const row = rows[virtualRow.index];
                  if (!row) return null;
                  const displayIndex =
                    (rowIndices?.[virtualRow.index] ?? rowOffset + virtualRow.index) + 1;
                  return (
                    <div
                      className="absolute top-0 left-0 grid w-full items-center border-b border-slate-100 bg-white text-sm transition-colors hover:bg-indigo-50/35"
                      key={virtualRow.key}
                      style={{
                        gridTemplateColumns,
                        height: virtualRow.size,
                        transform: `translateY(${virtualRow.start}px)`,
                      }}
                    >
                      <div className="flex items-center justify-between px-3 font-mono text-xs text-slate-400">
                        {displayIndex}
                        <button
                          className="rounded-md p-1.5 transition hover:bg-white hover:text-indigo-600 hover:shadow-sm"
                          type="button"
                          onClick={() => void copyRow(virtualRow.index)}
                          aria-label={`Copy row ${displayIndex} as JSON`}
                        >
                          {copied === virtualRow.index ? <Check className="size-3 text-emerald-600" /> : <Copy className="size-3" />}
                        </button>
                      </div>
                      {columns.map((column) => (
                        <div className="min-w-0 overflow-hidden border-l border-slate-100 px-4 py-3" key={column}>
                          <Cell
                            value={row[column]}
                            namespace={namespace}
                            dataset={dataset}
                            revision={revision}
                            config={config}
                            split={split}
                            inspect={() => setInspected({ column, value: row[column] })}
                            previewImage={setPreviewedImage}
                          />
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
      {inspected ? <CellInspector cell={inspected} close={() => setInspected(null)} /> : null}
      {previewedImage ? (
        <ImageLightbox image={previewedImage} close={() => setPreviewedImage(null)} />
      ) : null}
    </>
  );
}
