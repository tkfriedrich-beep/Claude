import { describe, expect, it, vi } from "vitest";
import { handleRadioKeys } from "@/lib/a11y";

// A minimal stand-in for the parts of React.KeyboardEvent the helper reads.
function keyEvent(key: string) {
  const preventDefault = vi.fn();
  return { event: { key, preventDefault }, preventDefault };
}

describe("handleRadioKeys (R4-F11)", () => {
  it("moves to the next option on ArrowRight/ArrowDown, wrapping at the end", () => {
    const onSelect = vi.fn();
    const { event, preventDefault } = keyEvent("ArrowRight");
    expect(handleRadioKeys(event, 3, 0, onSelect)).toBe(true);
    expect(onSelect).toHaveBeenCalledWith(1);
    expect(preventDefault).toHaveBeenCalled();

    onSelect.mockClear();
    handleRadioKeys(keyEvent("ArrowDown").event, 3, 2, onSelect);
    expect(onSelect).toHaveBeenCalledWith(0); // wraps
  });

  it("moves to the previous option on ArrowLeft/ArrowUp, wrapping at the start", () => {
    const onSelect = vi.fn();
    handleRadioKeys(keyEvent("ArrowLeft").event, 3, 0, onSelect);
    expect(onSelect).toHaveBeenCalledWith(2); // wraps

    onSelect.mockClear();
    handleRadioKeys(keyEvent("ArrowUp").event, 3, 2, onSelect);
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("jumps to first/last on Home/End", () => {
    const onSelect = vi.fn();
    handleRadioKeys(keyEvent("Home").event, 4, 2, onSelect);
    expect(onSelect).toHaveBeenCalledWith(0);

    onSelect.mockClear();
    handleRadioKeys(keyEvent("End").event, 4, 1, onSelect);
    expect(onSelect).toHaveBeenCalledWith(3);
  });

  it("ignores unrelated keys and never selects", () => {
    const onSelect = vi.fn();
    const { event, preventDefault } = keyEvent("a");
    expect(handleRadioKeys(event, 3, 0, onSelect)).toBe(false);
    expect(onSelect).not.toHaveBeenCalled();
    expect(preventDefault).not.toHaveBeenCalled();
  });
});
