import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { deriveOttoState, OttoPulse } from "@/components/cockpit/otto-pulse";

describe("deriveOttoState", () => {
  it("prioritizes approvals over execution", () => {
    expect(deriveOttoState([{ status: "executing" }], 1)).toBe("waiting");
    expect(deriveOttoState([{ status: "awaiting_approval" }], 0)).toBe("waiting");
  });
  it("maps pipeline stages to thinking/acting", () => {
    expect(deriveOttoState([{ status: "executing" }], 0)).toBe("acting");
    expect(deriveOttoState([{ status: "planning" }], 0)).toBe("thinking");
    expect(deriveOttoState([], 0)).toBe("idle");
  });
});

describe("OttoPulse", () => {
  it("announces state accessibly and encodes it on the svg", () => {
    render(<OttoPulse state="waiting" />);
    expect(screen.getByTestId("otto-state")).toHaveTextContent("Waiting for your approval");
    expect(document.querySelector("[data-otto-state='waiting']")).not.toBeNull();
  });
});
