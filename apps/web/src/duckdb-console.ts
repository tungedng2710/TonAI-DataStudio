import * as duckdb from "@duckdb/duckdb-wasm";
import type { DataType } from "apache-arrow";
import duckdbEhWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import duckdbMvpWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url";
import duckdbEhWasm from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";
import duckdbMvpWasm from "@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url";

import { quoteSqlIdentifier, type SqlViewDefinition } from "./sql-views";

const BUNDLES: duckdb.DuckDBBundles = {
  mvp: { mainModule: duckdbMvpWasm, mainWorker: duckdbMvpWorker },
  eh: { mainModule: duckdbEhWasm, mainWorker: duckdbEhWorker },
};

const TABULAR_SUFFIXES = new Set([".parquet", ".csv", ".tsv", ".json", ".jsonl", ".txt"]);

export interface SqlQueryResult {
  columns: string[];
  columnTypes: string[];
  rows: Record<string, unknown>[];
  totalRows: number;
  truncated: boolean;
  elapsedMs: number;
}

export type SqlExportFormat = "csv" | "json" | "parquet";

export interface SqlExportResult {
  bytes: Uint8Array;
  mediaType: string;
  fileName: string;
}

function suffixOf(path: string): string {
  const fileName = path.split("/").at(-1) ?? path;
  const dot = fileName.lastIndexOf(".");
  return dot < 0 ? "" : fileName.slice(dot).toLowerCase();
}

function quoteSqlString(value: string): string {
  return `'${value.replaceAll("'", "''")}'`;
}

function queryWithoutTrailingSemicolon(sql: string): string {
  return sql.trim().replace(/;+\s*$/, "");
}

function readerSql(path: string, suffix: string): string {
  const source = quoteSqlString(path);
  if (suffix === ".parquet") return `SELECT * FROM read_parquet(${source})`;
  if (suffix === ".json" || suffix === ".jsonl") {
    return `SELECT * FROM read_json_auto(${source})`;
  }
  if (suffix === ".tsv") {
    return `SELECT * FROM read_csv_auto(${source}, delim = '\\t', header = true)`;
  }
  if (suffix === ".txt") {
    return `SELECT * FROM read_csv(${source}, delim = '\\x1f', header = false, names = ['text'])`;
  }
  return `SELECT * FROM read_csv_auto(${source}, header = true)`;
}

function jsonValue(value: unknown): unknown {
  if (typeof value === "bigint") return value.toString();
  if (value instanceof Uint8Array) return `[${value.byteLength.toLocaleString()} bytes]`;
  if (Array.isArray(value)) return value.map(jsonValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, jsonValue(item)]),
    );
  }
  return value;
}

export class BrowserSqlEngine {
  private database: duckdb.AsyncDuckDB | null = null;
  private connection: duckdb.AsyncDuckDBConnection | null = null;

  async initialize(
    views: SqlViewDefinition[],
    loadFile: (path: string) => Promise<Uint8Array>,
    report: (message: string) => void,
  ): Promise<void> {
    if (this.connection) return;
    report("Starting DuckDB WASM…");
    const bundle = await duckdb.selectBundle(BUNDLES);
    if (!bundle.mainWorker) throw new Error("This browser does not support a DuckDB WASM worker.");
    const worker = new Worker(bundle.mainWorker);
    const database = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
    this.database = database;
    await database.instantiate(bundle.mainModule, bundle.pthreadWorker);
    const connection = await database.connect();
    this.connection = connection;

    let fileNumber = 0;
    const totalFiles = views.reduce(
      (total, view) => total + view.files.filter((path) => TABULAR_SUFFIXES.has(suffixOf(path))).length,
      0,
    );
    for (const view of views) {
      const sources: string[] = [];
      const tabularFiles = view.files.filter((path) => TABULAR_SUFFIXES.has(suffixOf(path)));
      for (const [index, path] of tabularFiles.entries()) {
        fileNumber += 1;
        report(`Loading ${path} (${fileNumber.toLocaleString()}/${totalFiles.toLocaleString()})…`);
        const virtualPath = `${view.name}_${index}${suffixOf(path)}`;
        await database.registerFileBuffer(virtualPath, await loadFile(path));
        sources.push(readerSql(virtualPath, suffixOf(path)));
      }

      if (!sources.length && view.builder === "imagefolder") {
        const imageRows = view.files
          .filter((path) => !TABULAR_SUFFIXES.has(suffixOf(path)))
          .map((path) => ({ image: path, label: path.split("/").slice(-2, -1)[0] ?? "" }));
        const virtualPath = `${view.name}_images.json`;
        await database.registerFileText(virtualPath, JSON.stringify(imageRows));
        sources.push(`SELECT * FROM read_json_auto(${quoteSqlString(virtualPath)})`);
      }

      const sourceSql = sources.length
        ? sources.join(" UNION ALL BY NAME ")
        : "SELECT NULL::VARCHAR AS value WHERE false";
      await connection.query(
        `CREATE OR REPLACE VIEW ${quoteSqlIdentifier(view.name)} AS ${sourceSql}`,
      );
    }
  }

  async query(sql: string): Promise<SqlQueryResult> {
    if (!this.connection) throw new Error("DuckDB WASM is not ready.");
    const started = performance.now();
    const table = await this.connection.query<Record<string, DataType>>(sql);
    const columns = table.schema.fields.map((field) => field.name);
    const columnTypes = table.schema.fields.map((field) => field.type.constructor.name);
    const maxDisplayedRows = 100;
    const rows = Array.from(
      { length: Math.min(table.numRows, maxDisplayedRows) },
      (_, index) => {
        const record = table.get(index) as unknown as Record<string, unknown> | null;
        return Object.fromEntries(
          columns.map((column) => [column, jsonValue(record?.[column])]),
        );
      },
    );
    return {
      columns,
      columnTypes,
      rows,
      totalRows: table.numRows,
      truncated: table.numRows > maxDisplayedRows,
      elapsedMs: performance.now() - started,
    };
  }

  async exportQuery(sql: string, format: SqlExportFormat): Promise<SqlExportResult> {
    if (!this.connection || !this.database) throw new Error("DuckDB WASM is not ready.");
    const query = queryWithoutTrailingSemicolon(sql);
    if (!query) throw new Error("Run a query before downloading its result.");
    const fileName = `query-result.${format}`;
    const virtualPath = `query-result-${crypto.randomUUID()}.${format}`;
    const options: Record<SqlExportFormat, string> = {
      csv: "FORMAT CSV, HEADER TRUE",
      json: "FORMAT JSON, ARRAY TRUE",
      parquet: "FORMAT PARQUET, COMPRESSION ZSTD",
    };
    const mediaTypes: Record<SqlExportFormat, string> = {
      csv: "text/csv;charset=utf-8",
      json: "application/json",
      parquet: "application/vnd.apache.parquet",
    };
    try {
      await this.connection.query(
        `COPY (${query}) TO ${quoteSqlString(virtualPath)} (${options[format]})`,
      );
      return {
        bytes: await this.database.copyFileToBuffer(virtualPath),
        mediaType: mediaTypes[format],
        fileName,
      };
    } finally {
      await this.database.dropFile(virtualPath).catch(() => undefined);
    }
  }

  async close(): Promise<void> {
    const connection = this.connection;
    const database = this.database;
    this.connection = null;
    this.database = null;
    if (connection) await connection.close().catch(() => undefined);
    if (database) await database.terminate().catch(() => undefined);
  }
}
