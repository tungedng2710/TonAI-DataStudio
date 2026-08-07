import { Tag } from "lucide-react";

import type { DataStage } from "../types";

function stageLabel(stage: DataStage): string {
  return stage
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function DatasetTags({
  dataStage,
  tags,
  maxTags = 2,
  className = "",
}: {
  dataStage: DataStage | null;
  tags: string[];
  maxTags?: number;
  className?: string;
}) {
  const visibleTags = tags.slice(0, maxTags);
  const hiddenTagCount = Math.max(0, tags.length - visibleTags.length);

  if (!dataStage && !tags.length) return null;

  return (
    <div
      aria-label="Dataset tags"
      className={`flex min-w-0 flex-wrap items-center gap-1.5 ${className}`}
    >
      {dataStage ? (
        <span
          className="inline-flex items-center gap-1 rounded-md bg-cyan-50 px-2 py-1 text-[11px] font-semibold text-cyan-800 ring-1 ring-cyan-100"
          title={`Data stage: ${stageLabel(dataStage)}`}
        >
          <span className="size-1.5 rounded-full bg-cyan-500" />
          {stageLabel(dataStage)}
        </span>
      ) : null}
      {visibleTags.map((tag) => (
        <span
          className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-600"
          key={tag}
          title={tag}
        >
          <Tag className="size-3 text-slate-400" />
          <span className="max-w-28 truncate">{tag}</span>
        </span>
      ))}
      {hiddenTagCount ? (
        <span
          className="rounded-md bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-500"
          title={`${hiddenTagCount} more tag${hiddenTagCount === 1 ? "" : "s"}`}
        >
          +{hiddenTagCount}
        </span>
      ) : null}
    </div>
  );
}
