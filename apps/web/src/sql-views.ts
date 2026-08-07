import type { DatasetConfig } from "./types";

export interface SqlViewDefinition {
  name: string;
  config: string;
  split: string;
  builder: string;
  files: string[];
}

function safeSqlName(value: string): string {
  const normalized = value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
  if (!normalized) return "data";
  return /^[a-z_]/.test(normalized) ? normalized : `view_${normalized}`;
}

export function quoteSqlIdentifier(value: string): string {
  return `"${value.replaceAll('"', '""')}"`;
}

export function queryForView(viewName: string): string {
  const reference = /^[a-z_][a-z0-9_]*$/i.test(viewName)
    ? viewName
    : quoteSqlIdentifier(viewName);
  return `SELECT * FROM ${reference} LIMIT 10;`;
}

export function sqlViewsForConfigs(configs: DatasetConfig[]): SqlViewDefinition[] {
  const useConfigPrefix = configs.length > 1;
  const used = new Set<string>();
  return configs.flatMap((config) => config.splits.map((split) => {
    const base = safeSqlName(
      useConfigPrefix ? `${config.name}_${split.name}` : split.name,
    );
    let name = base;
    let suffix = 2;
    while (used.has(name)) {
      name = `${base}_${suffix}`;
      suffix += 1;
    }
    used.add(name);
    return {
      name,
      config: config.name,
      split: split.name,
      builder: config.builder_name,
      files: split.data_files,
    };
  }));
}
