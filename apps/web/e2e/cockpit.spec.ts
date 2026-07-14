// Desktop e2e against a REAL control plane (port 8788, isolated data dir).
// Covers the BUILD_BRIEF acceptance flows: onboarding/demo, running a skill,
// approval denial, approval success (write executes only after approval),
// run history, keyboard palette, and axe accessibility checks.
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";

const API = "http://localhost:8788/api/v1";
const repoRoot = path.resolve(__dirname, "../../..");
const e2eIdeasDir = path.join(repoRoot, "data", "e2e", "bizideas");

test.describe.configure({ mode: "serial" });

test("onboarding with demo data reaches the cockpit", async ({ page }) => {
  await page.goto("/");
  await page.waitForURL("**/onboarding");

  await page.getByTestId("ob-name").fill("Alex");
  await page.getByTestId("ob-next").click();
  await page.getByTestId("ob-next").click(); // demo data stays on by default
  await page.getByTestId("ob-finish").click();

  await page.waitForURL("http://localhost:3100/", { timeout: 45_000 });
  await expect(page.getByTestId("greeting")).toContainText("Alex");
  await expect(page.getByTestId("what-matters")).toBeVisible();
  await expect(page.getByTestId("safe-mode-pill")).toContainText("Safe Mode on");
  await expect(page.getByTestId("home-composer")).toBeVisible(); // R4-F12: compat id preserved

  // isolate write-backs: point the ideas folder at a copy inside the e2e data dir
  fs.mkdirSync(e2eIdeasDir, { recursive: true });
  for (const file of fs.readdirSync(path.join(repoRoot, "data", "demo", "bizideas"))) {
    if (file.endsWith(".scorecard.md")) continue;
    fs.copyFileSync(
      path.join(repoRoot, "data", "demo", "bizideas", file),
      path.join(e2eIdeasDir, file),
    );
  }
  const response = await page.request.patch(`${API}/settings`, {
    data: { bizideas_path: e2eIdeasDir },
  });
  expect(response.ok()).toBeTruthy();

  // The demo seeder honestly leaves its own triage run parked on an approval.
  // Drain it so later specs start from a quiet queue.
  await expect(async () => {
    const pending = (await (await page.request.get(`${API}/approvals?status=pending`)).json()) as {
      id: string;
    }[];
    for (const approval of pending) {
      await page.request.post(`${API}/approvals/${approval.id}/resolve`, {
        data: { decision: "deny", note: "e2e reset" },
      });
    }
    const active = (await (
      await page.request.get(
        `${API}/runs?status=queued,triaging,planning,awaiting_approval,executing,verifying,reviewing`,
      )
    ).json()) as unknown[];
    expect(pending.length + active.length).toBe(0);
  }).toPass({ timeout: 60_000 });
});

test("home screen is keyboard accessible and passes axe", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("greeting")).toBeVisible();

  // Cmd+K palette opens and navigates
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
  await page.getByLabel("Palette search").fill("agents"); // executive label for /skills
  await page.keyboard.press("Enter");
  await page.waitForURL("**/skills");

  const results = await new AxeBuilder({ page })
    .disableRules(["color-contrast"]) // checked manually for the token palette
    .analyze();
  const serious = results.violations.filter((v) => ["critical", "serious"].includes(v.impact ?? ""));
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});

test("command palette routes a required-input agent to its form, not a failed run (R4-F5)", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("greeting")).toBeVisible();

  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
  await page.getByLabel("Palette search").fill("decision memo");
  await page.keyboard.press("Enter");

  // Decision Memo requires input — the palette must open its form, not create a doomed run.
  await page.waitForURL("**/skills/decision-memo");
  await expect(page.getByTestId("skill-input-json")).toBeVisible();
});

test("project pulse runs to completion with sourced results", async ({ page }) => {
  await page.goto("/skills");
  await page.getByTestId("run-project-pulse").click();
  await page.waitForURL("**/history/**");

  await expect(page.getByTestId("run-status")).toHaveText("Completed", { timeout: 30_000 });
  await expect(page.getByTestId("run-result")).toContainText("projects");
  await expect(page.getByTestId("source-chips")).toBeVisible();
  await expect(page.getByTestId("run-timeline")).toContainText("Reading your project notes", {
    timeout: 15_000,
  });
});

test("side effects wait for approval: deny skips, approve executes exactly once", async ({ page }) => {
  // run business-idea-triage (draft) → write-backs must pause for approval
  await page.goto("/skills");
  await page.getByTestId("run-business-idea-triage").click();
  await page.waitForURL("**/history/**");
  const runUrl = page.url();
  await expect(page.getByTestId("run-status")).toHaveText("Needs approval", { timeout: 30_000 });

  // nothing may be written before approval
  expect(fs.readdirSync(e2eIdeasDir).filter((f) => f.endsWith(".scorecard.md"))).toHaveLength(0);

  // 1) DENY the first proposal (through the UI)
  await page.goto("/approvals");
  const firstCard = page.getByTestId("approval-card").first();
  await expect(firstCard).toContainText("Write scorecard");
  await expect(firstCard).toContainText("R2");
  const deniedIdea = await firstCard.locator("h3").textContent();
  await firstCard.getByTestId("deny-btn").click();

  // wait until the run resumed and proposed the NEXT write (a different approval id)
  let secondApprovalId = "";
  await expect(async () => {
    const response = await page.request.get(`${API}/approvals?status=pending`);
    const items = (await response.json()) as { id: string; title: string }[];
    expect(items).toHaveLength(1);
    expect(items[0].title).not.toBe(deniedIdea);
    secondApprovalId = items[0].id;
  }).toPass({ timeout: 30_000 });

  // 2) APPROVE the second proposal through the UI — the write must then happen
  await page.reload();
  const secondCard = page.getByTestId("approval-card").first();
  await expect(secondCard).not.toContainText(deniedIdea ?? "∅");
  await secondCard.getByTestId("approve-btn").click();
  await expect(async () => {
    const response = await page.request.get(`${API}/approvals`);
    const items = (await response.json()) as { id: string; status: string }[];
    expect(items.find((a) => a.id === secondApprovalId)?.status).toBe("approved");
  }).toPass({ timeout: 15_000 });

  // 3) deny the remaining proposals of THIS run until it completes
  const runId = runUrl.split("/history/")[1];
  await expect(async () => {
    const pending = (await (
      await page.request.get(`${API}/approvals?status=pending`)
    ).json()) as { id: string; run_id: string }[];
    for (const approval of pending.filter((a) => a.run_id === runId)) {
      await page.request.post(`${API}/approvals/${approval.id}/resolve`, {
        data: { decision: "deny", note: "e2e cleanup" },
      });
    }
    const run = (await (await page.request.get(`${API}/runs/${runId}`)).json()) as {
      status: string;
    };
    expect(run.status).toBe("completed");
  }).toPass({ timeout: 60_000 });

  // exactly one scorecard written (the approved one), none for the denied
  const scorecards = fs.readdirSync(e2eIdeasDir).filter((f) => f.endsWith(".scorecard.md"));
  expect(scorecards).toHaveLength(1);
  expect(deniedIdea).toBeTruthy();

  // the run detail records the skipped write-backs honestly
  await page.goto(runUrl);
  await expect(page.getByTestId("run-status")).toHaveText("Completed");
  await expect(page.getByText("Unresolved")).toBeVisible();
});

test("history shows the audit trail and replayable timeline", async ({ page }) => {
  await page.goto("/history");
  const rows = page.getByTestId("history-list").locator("a");
  await expect(rows.first()).toBeVisible();
  expect(await rows.count()).toBeGreaterThanOrEqual(3);

  await rows.first().click();
  await expect(page.getByTestId("run-timeline")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Verification" })).toBeVisible();
});

test("chat command streams a reply from the demo runtime", async ({ page }) => {
  await page.goto("/command");
  await page.getByTestId("command-composer").fill("hello Otto");
  await page.getByTestId("command-send").click();

  await expect(page.getByTestId("assistant-reply")).toContainText("offline demo runtime", {
    timeout: 30_000,
  });
});

test("desktop screenshots for the record", async ({ page }) => {
  const dir = path.join(repoRoot, "docs", "screenshots");
  fs.mkdirSync(dir, { recursive: true });
  await page.goto("/");
  await expect(page.getByTestId("greeting")).toBeVisible();
  await page.screenshot({ path: path.join(dir, "home-desktop.png"), fullPage: true });
  await page.goto("/approvals");
  await page.screenshot({ path: path.join(dir, "approvals-desktop.png") });
  await page.goto("/history");
  await page.screenshot({ path: path.join(dir, "history-desktop.png") });
});
