import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DatasetTags } from "./DatasetTags";

describe("DatasetTags", () => {
  afterEach(cleanup);

  it("shows the data stage, visible tags, and hidden count", () => {
    render(
      <DatasetTags
        dataStage="training_ready"
        maxTags={2}
        tags={["license-plates", "vietnam", "night"]}
      />,
    );

    expect(screen.getByText("Training Ready")).toBeInTheDocument();
    expect(screen.getByText("license-plates")).toBeInTheDocument();
    expect(screen.getByText("vietnam")).toBeInTheDocument();
    expect(screen.queryByText("night")).not.toBeInTheDocument();
    expect(screen.getByText("+1")).toHaveAttribute("title", "1 more tag");
  });

  it("does not reserve space when no metadata is assigned", () => {
    const { container } = render(<DatasetTags dataStage={null} tags={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
