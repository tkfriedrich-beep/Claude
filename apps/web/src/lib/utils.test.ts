import { describe, expect, it } from "vitest";
import { greeting, timeAgo, tokenizeCommand, RUN_STATUS_STYLE } from "@/lib/utils";

describe("greeting", () => {
  it("greets by time of day and name", () => {
    expect(greeting("Alex", new Date("2026-07-12T08:00:00"))).toBe("Good morning, Alex");
    expect(greeting("Alex", new Date("2026-07-12T14:00:00"))).toBe("Good afternoon, Alex");
    expect(greeting(null, new Date("2026-07-12T20:00:00"))).toBe("Good evening");
  });
});

describe("timeAgo", () => {
  it("handles nulls and recent times", () => {
    expect(timeAgo(null)).toBe("—");
    expect(timeAgo(new Date().toISOString())).toBe("just now");
    expect(timeAgo(new Date(Date.now() - 7200_000).toISOString())).toBe("2h ago");
  });
});

describe("tokenizeCommand (R4-F4)", () => {
  it("splits an executable from its arguments", () => {
    // the exact placeholder the MCP form shows — it must register as command + args, not one blob
    expect(tokenizeCommand("npx -y @modelcontextprotocol/server-filesystem /path")).toEqual([
      "npx",
      "-y",
      "@modelcontextprotocol/server-filesystem",
      "/path",
    ]);
  });
  it("respects single and double quotes", () => {
    expect(tokenizeCommand('python -c "import sys; print(sys.argv)"')).toEqual([
      "python",
      "-c",
      "import sys; print(sys.argv)",
    ]);
    expect(tokenizeCommand("cmd 'one arg' two")).toEqual(["cmd", "one arg", "two"]);
  });
  it("collapses surrounding whitespace and handles the empty string", () => {
    expect(tokenizeCommand("   ")).toEqual([]);
    expect(tokenizeCommand("")).toEqual([]);
    expect(tokenizeCommand("  solo  ")).toEqual(["solo"]);
  });
});

describe("run status map", () => {
  it("covers every control-plane status", () => {
    const statuses = [
      "queued", "triaging", "planning", "awaiting_approval", "executing",
      "verifying", "reviewing", "completed", "failed", "cancelled", "interrupted",
    ];
    for (const status of statuses) expect(RUN_STATUS_STYLE[status]).toBeDefined();
  });
});
