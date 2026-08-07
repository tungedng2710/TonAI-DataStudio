import { describe, expect, it } from "vitest";

import { isValidDatasetTag, normalizeDatasetTag } from "./dataset-tags";

describe("dataset tags", () => {
  it.each([
    ["Synthetic data", "synthetic-data"],
    ["  English   OCR  ", "english-ocr"],
    ["license--plates", "license-plates"],
  ])("normalizes %s", (provided, expected) => {
    expect(normalizeDatasetTag(provided)).toBe(expected);
  });

  it("rejects unsupported characters", () => {
    expect(isValidDatasetTag("image/ocr")).toBe(false);
    expect(isValidDatasetTag("image-ocr")).toBe(true);
  });
});
