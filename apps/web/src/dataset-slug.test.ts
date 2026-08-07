import { describe, expect, it } from "vitest";

import { normalizeDatasetSlug } from "./dataset-slug";

describe("normalizeDatasetSlug", () => {
  it.each([
    ["License plate", "license-plate"],
    ["  License   plate  ", "license-plate"],
    ["License--plate", "license-plate"],
    ["DATASET.v2", "dataset.v2"],
  ])("normalizes %s", (provided, expected) => {
    expect(normalizeDatasetSlug(provided)).toBe(expected);
  });
});
