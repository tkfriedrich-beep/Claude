import { describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { SegmentedControl } from "@/components/ui/segmented";

// Controlled harness — SegmentedControl is a controlled radio group.
function Harness({ onChange }: { onChange?: (v: string) => void }) {
  const [value, setValue] = useState("a");
  return (
    <SegmentedControl
      options={[
        { value: "a", label: "A" },
        { value: "b", label: "B" },
        { value: "c", label: "C" },
      ]}
      value={value}
      onChange={(v) => {
        setValue(v);
        onChange?.(v);
      }}
      label="Test group"
    />
  );
}

describe("SegmentedControl keyboard (R4-F11)", () => {
  it("uses a roving tabindex: only the checked radio is tabbable", () => {
    render(<Harness />);
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(3);
    expect(radios[0]).toHaveAttribute("aria-checked", "true");
    expect(radios[0]).toHaveAttribute("tabindex", "0");
    expect(radios[1]).toHaveAttribute("tabindex", "-1");
    expect(radios[2]).toHaveAttribute("tabindex", "-1");
  });

  it("moves selection with arrow keys (wrapping) and Home/End", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const radios = () => screen.getAllByRole("radio");

    radios()[0].focus();
    fireEvent.keyDown(radios()[0], { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith("b");
    expect(radios()[1]).toHaveAttribute("aria-checked", "true");

    fireEvent.keyDown(radios()[1], { key: "ArrowLeft" });
    expect(onChange).toHaveBeenLastCalledWith("a");

    fireEvent.keyDown(radios()[0], { key: "ArrowLeft" }); // wraps to last
    expect(onChange).toHaveBeenLastCalledWith("c");

    fireEvent.keyDown(radios()[2], { key: "Home" });
    expect(onChange).toHaveBeenLastCalledWith("a");
  });
});
