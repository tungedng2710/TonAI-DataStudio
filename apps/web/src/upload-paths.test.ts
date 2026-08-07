import { describe, expect, it } from "vitest";

import { repositoryPathForUpload } from "./upload-paths";

describe("repositoryPathForUpload", () => {
  it("places individually selected files at the repository root", () => {
    const file = new File(["content"], "README.md");

    expect(repositoryPathForUpload(file)).toBe("README.md");
  });

  it("removes the selected folder name and preserves nested paths", () => {
    const file = new File(["data"], "train.parquet");
    Object.defineProperty(file, "webkitRelativePath", {
      value: "my-dataset/data/train.parquet",
    });

    expect(repositoryPathForUpload(file)).toBe("data/train.parquet");
  });
});
