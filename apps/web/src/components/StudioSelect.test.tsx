import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StudioSelect } from "./StudioSelect";

const options = [
  { value: "private", label: "Private", description: "Owner only" },
  { value: "internal", label: "Internal", description: "Signed-in users" },
  { value: "public", label: "Public", description: "Everyone" },
];

describe("StudioSelect", () => {
  afterEach(cleanup);

  it("opens a polished listbox and selects an option with the pointer", () => {
    const onChange = vi.fn();
    render(
      <StudioSelect
        ariaLabel="Dataset visibility"
        value="private"
        options={options}
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByRole("combobox", { name: "Dataset visibility" }));
    expect(screen.getByRole("listbox", { name: "Dataset visibility" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("option", { name: /Public/ }));

    expect(onChange).toHaveBeenCalledWith("public");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("supports arrow-key navigation and selection", () => {
    const onChange = vi.fn();
    render(
      <StudioSelect
        ariaLabel="Dataset visibility"
        value="private"
        options={options}
        onChange={onChange}
      />,
    );

    const trigger = screen.getByRole("combobox", { name: "Dataset visibility" });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.keyDown(trigger, { key: "Enter" });

    expect(onChange).toHaveBeenCalledWith("internal");
  });
});
