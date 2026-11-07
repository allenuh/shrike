import { expect, test } from "@playwright/test";

test("navigate from review list to file-grouped finding detail", async ({
  page,
}, testInfo) => {
  await page.goto("/reviews");
  await expect(
    page.getByRole("heading", { name: "Every review. A clear trail." }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Pull request #248", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Pull request #248", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "src/storage.py", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("User input is interpolated into a database query.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    page.getByLabel(/Source evidence at src\/storage.py/),
  ).toContainText("SELECT * FROM accounts");
  await expect(page.getByText(/Deterministic mock-assisted/)).toBeVisible();
  await page.getByLabel("Filter findings by severity").selectOption("high");
  await expect(
    page.getByRole("heading", { name: "src/payments.py", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "src/storage.py", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("finding-detail.png"),
    fullPage: true,
  });
});

test("filters, pagination, keyboard access and responsive navigation", async ({
  page,
}, testInfo) => {
  await page.goto("/reviews");
  await expect(
    page.getByRole("link", { name: "Pull request #248", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Pull request #240", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Filter by state").selectOption("failed");
  await expect(
    page.getByRole("link", { name: "Pull request #244", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Pull request #248", exact: true }),
  ).toHaveCount(0);
  expect(new URL(page.url()).searchParams.has("cursor")).toBe(false);
  if (testInfo.project.name === "mobile")
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "A clearer view of your code." }),
  ).toBeVisible();
  await expect(page.getByText("Read-only demo", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.keyboard.press("Control+Home");
  await page.screenshot({
    path: testInfo.outputPath("overview.png"),
    fullPage: true,
  });
});

test("demo endpoints refuse mutations and never expose credentials", async ({
  request,
}) => {
  const response = await request.get(
    "/api/backend/v1/dashboard/reviews?state=failed",
  );
  expect(response.ok()).toBe(true);
  expect(response.headers()["cache-control"]).toBe("no-store");
  expect(
    (await response.json()).items.every(
      (r: { state: string }) => r.state === "failed",
    ),
  ).toBe(true);
  expect(
    (
      await request.post("/api/backend/v1/dashboard/settings", {
        data: { ai_provider: "openai" },
      })
    ).status(),
  ).toBe(405);
  expect((await request.get("/api/backend/webhooks/github")).status()).toBe(
    404,
  );
  const session = await (await request.get("/api/backend/auth/session")).json();
  expect(Object.keys(session).sort()).toEqual(["login", "mode"]);
});

test("repository navigation, saved display preferences, and honest status", async ({
  page,
}, testInfo) => {
  await page.goto("/repositories");
  await expect(
    page.getByRole("heading", { name: "payments-api", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Browse reviews" }).first().click();
  await expect(page.getByLabel("Filter by repository")).toHaveValue(
    "00000000-0000-4000-8000-000000000001",
  );
  await page.goto("/settings");
  await expect(
    page.getByText("Synthetic demo integration", { exact: true }),
  ).toBeVisible();
  await page.getByRole("radio", { name: /Compact/ }).check();
  await page.getByRole("button", { name: "Save preference" }).click();
  await expect(page.getByRole("status")).toContainText("Saved to this browser");
  await page.reload();
  await expect(page.getByRole("radio", { name: /Compact/ })).toBeChecked();
  await page.goto("/status");
  await expect(
    page.getByRole("heading", { name: "Demo operational snapshot" }),
  ).toBeVisible();
  await expect(
    page.getByText("Not instrumented", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Not measured", { exact: true })).toBeVisible();
  if (testInfo.project.name === "mobile") {
    const menu = page.getByRole("button", { name: "Open navigation" });
    await menu.focus();
    await page.keyboard.press("Enter");
    await expect(
      page.getByRole("dialog", { name: "Workspace navigation" }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Overview", exact: true }),
    ).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(menu).toBeFocused();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  await page.screenshot({
    path: testInfo.outputPath("system-status.png"),
    fullPage: true,
  });
});
