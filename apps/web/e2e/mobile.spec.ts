// Mobile e2e (iPhone 13 viewport): bottom-tab navigation, briefing readability,
// approvals reachable — the capture/approve/read loop, not desktop admin.
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const repoRoot = path.resolve(__dirname, "../../..");

test.describe.configure({ mode: "serial" });

test("mobile home shows briefing with bottom tabs", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("greeting")).toBeVisible({ timeout: 30_000 });

  const mobileNav = page.getByRole("navigation", { name: "Primary mobile" });
  await expect(mobileNav).toBeVisible();
  const desktopNav = page.getByRole("navigation", { name: "Primary", exact: true });
  await expect(desktopNav).toBeHidden();

  // no horizontal overflow
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});

test("mobile navigation reaches approvals and command", async ({ page }) => {
  await page.goto("/");
  const mobileNav = page.getByRole("navigation", { name: "Primary mobile" });
  await mobileNav.getByRole("link", { name: /Approvals/ }).click();
  await page.waitForURL("**/approvals");
  await expect(page.getByRole("heading", { name: "Approvals" })).toBeVisible();

  await mobileNav.getByRole("link", { name: /Command/ }).click();
  await page.waitForURL("**/command");
  await expect(page.getByTestId("command-composer")).toBeVisible();
});

test("mobile screenshots for the record", async ({ page }) => {
  const dir = path.join(repoRoot, "docs", "screenshots");
  fs.mkdirSync(dir, { recursive: true });
  await page.goto("/");
  await expect(page.getByTestId("greeting")).toBeVisible();
  await page.screenshot({ path: path.join(dir, "home-mobile.png"), fullPage: true });
  await page.goto("/approvals");
  await page.screenshot({ path: path.join(dir, "approvals-mobile.png") });
});
