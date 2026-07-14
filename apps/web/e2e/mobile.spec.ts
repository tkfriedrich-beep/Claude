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

test("mobile navigation reaches decisions and command", async ({ page }) => {
  await page.goto("/");
  const mobileNav = page.getByRole("navigation", { name: "Primary mobile" });
  await mobileNav.getByRole("link", { name: /Decisions/ }).click();
  await page.waitForURL("**/approvals");
  await expect(page.getByRole("heading", { name: "Decisions" })).toBeVisible();

  await mobileNav.getByRole("link", { name: /Command/ }).click();
  await page.waitForURL("**/command");
  await expect(page.getByTestId("command-composer")).toBeVisible();
});

test("mobile keeps Safe Mode and Settings one tap away (R4-F3)", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("greeting")).toBeVisible({ timeout: 30_000 });

  // Emergency Safe Mode is reachable in the phone command band (desktop nav is hidden < lg).
  const safe = page.getByTestId("safe-mode-pill-mobile");
  await expect(safe).toBeVisible();
  await expect(safe).toContainText("Safe Mode on");

  // Settings (and the rest of the roster) is reachable via the "More" system menu.
  const mobileNav = page.getByRole("navigation", { name: "Primary mobile" });
  await mobileNav.getByRole("button", { name: /More/ }).click();
  const sheet = page.getByRole("dialog", { name: "System menu" });
  await expect(sheet).toBeVisible();
  await sheet.getByRole("link", { name: "Settings" }).click();
  await page.waitForURL("**/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
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
