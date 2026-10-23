import { expect, test, type APIRequestContext } from "@playwright/test";

const API_URL = (process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const stamp = Date.now().toString(36);

async function createAndRunDemo(request: APIRequestContext): Promise<{
  id: string;
  name: string;
}> {
  const created = await request.post(`${API_URL}/api/demo-project`, { data: {} });
  expect(created.ok(), `demo project creation failed: ${await created.text()}`).toBeTruthy();
  const project = (await created.json()) as { id: string; name: string };

  const started = await request.post(`${API_URL}/api/projects/${project.id}/process`, {
    data: {
      n_clips: 2,
      platforms: ["tiktok", "linkedin"],
      min_clip_s: 12,
      max_clip_s: 35,
    },
  });
  expect(started.ok(), `pipeline start failed: ${await started.text()}`).toBeTruthy();

  await expect
    .poll(
      async () => {
        const response = await request.get(`${API_URL}/api/projects/${project.id}`);
        if (!response.ok()) return `http-${response.status()}`;
        const data = (await response.json()) as {
          latest_job?: { status?: string } | null;
        };
        return data.latest_job?.status ?? "missing";
      },
      { timeout: 210_000, intervals: [2_000, 3_000, 5_000] },
    )
    .toBe("completed");

  return project;
}

test("dashboard exposes the studio entry points", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Make the recording worth publishing." }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Run the demo" })).toBeVisible();
  await expect(page.getByRole("button", { name: "New project" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
});

test("creates a brand profile and shows it on the brands page", async ({ page }) => {
  const name = `E2E Voice ${stamp}`;

  await page.goto("/brands");
  await page.getByRole("button", { name: "New profile" }).first().click();

  const dialog = page.getByRole("dialog", { name: "New brand profile" });
  await expect(dialog).toBeVisible();
  await dialog.getByPlaceholder("e.g. Systems Studio").fill(name);
  await dialog.getByPlaceholder("e.g. Independent creators and operators").fill("Operators");
  await dialog
    .getByPlaceholder("Direct, warm, practical. Short sentences. No hype. Name the constraint before the solution.")
    .fill("Direct, specific, no hype.");
  await dialog.getByPlaceholder("revolutionary, guaranteed, hack, guru").fill("revolutionary, guaranteed");
  await dialog.getByRole("button", { name: "Create profile" }).click();

  await expect(dialog).toBeHidden();
  await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
  await expect(page.getByText("revolutionary", { exact: false }).first()).toBeVisible();
});

test("runs the demo pipeline, edits a clip, and re-renders it", async ({ page, request }) => {
  const project = await createAndRunDemo(request);

  await page.goto(`/projects/${project.id}`);
  await expect(page.getByRole("heading", { name: project.name })).toBeVisible();

  const clipLinks = page.locator('a[href*="/clips/"]');
  await expect(clipLinks.first()).toBeVisible();
  const clipCount = await clipLinks.count();
  expect(clipCount).toBeGreaterThan(0);

  await clipLinks.first().click();
  await expect(page.getByText("Clip studio", { exact: true })).toBeVisible();

  const caption = page.locator("textarea").first();
  await expect(caption).toBeVisible();
  const original = await caption.inputValue();
  const edited = `${original}\n\nE2E pass ${stamp}.`;
  await caption.fill(edited);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Changes saved", { exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByText("Clip studio", { exact: true })).toBeVisible();
  await expect(page.locator("textarea").first()).toHaveValue(edited);

  const renderButton = page.getByRole("button", { name: /^(Render clip|Re-render)$/ });
  await renderButton.click();
  await expect(page.getByText("Vertical clip rendered", { exact: true })).toBeVisible({
    timeout: 180_000,
  });
  await expect(page.getByText("9:16", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download rendered clip" })).toBeEnabled();
});
