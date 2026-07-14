import { describe, expect, it } from "vitest";

// R4-F9 regression: the small state-carrying text tokens (section labels, timestamps, trust
// strip, amber status) must meet WCAG AA (>=4.5:1) against the surfaces they render on. These
// values mirror apps/web/src/app/globals.css — if a token is lightened back below AA this fails.
function luminance(hex: string): number {
  const n = hex.replace("#", "");
  const channels = [0, 2, 4].map((i) => {
    const c = parseInt(n.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function ratio(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

// [name, text token, worst-case background it sits on]
const PAIRS: [string, string, string][] = [
  // dark "midnight graphite" — worst case is the lightest surface (--surface-raised)
  ["dark ink-faint on raised", "#8a8373", "#1d1a15"],
  ["dark muted-2 on raised", "#8f8a7c", "#1d1a15"],
  ["dark muted on raised", "#9b968a", "#1d1a15"],
  // light "parchment" — worst case is the darkest surface (--background)
  ["light ink-faint on bg", "#716d5c", "#f4f1ea"],
  ["light muted-2 on bg", "#706d5f", "#f4f1ea"],
  ["light muted on bg", "#6f6b60", "#f4f1ea"],
  // light amber text must be legible on the amber surface AND the page background
  ["light warn on warn-surface", "#93630d", "#faf3e3"],
  ["light warn on bg", "#93630d", "#f4f1ea"],
];

describe("design token contrast (R4-F9)", () => {
  it.each(PAIRS)("%s meets WCAG AA", (_name, text, bg) => {
    expect(ratio(text, bg)).toBeGreaterThanOrEqual(4.5);
  });

  it("sanity-checks the contrast math against a known pair", () => {
    expect(ratio("#000000", "#ffffff")).toBeCloseTo(21, 0);
  });
});
