import { describe, expect, it } from "vitest";

import { queryForView, quoteSqlIdentifier, sqlViewsForConfigs } from "./sql-views";
import type { DatasetConfig } from "./types";

function config(name: string, splits: string[]): DatasetConfig {
  return {
    name,
    builder_name: "parquet",
    builder_parameters: {},
    splits: splits.map((split) => ({
      name: split,
      data_files: [`data/${split}.parquet`],
      num_rows: 10,
      num_bytes: 100,
      schema: [],
    })),
  };
}

describe("SQL console views", () => {
  it("uses split names for a single config", () => {
    expect(sqlViewsForConfigs([config("default", ["train", "test"])]).map((view) => view.name))
      .toEqual(["train", "test"]);
    expect(queryForView("train")).toBe("SELECT * FROM train LIMIT 10;");
  });

  it("prefixes and normalizes views when configs could collide", () => {
    expect(sqlViewsForConfigs([
      config("English (US)", ["train"]),
      config("Tiếng Việt", ["train"]),
    ]).map((view) => view.name)).toEqual(["english_us_train", "tieng_viet_train"]);
  });

  it("quotes SQL identifiers safely", () => {
    expect(quoteSqlIdentifier('train"copy')).toBe('"train""copy"');
  });
});
