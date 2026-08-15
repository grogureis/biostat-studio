import { test, expect } from "playwright/test";

/**
 * This runs against the packaged Electron app in release verification.  Local
 * unit/CI environments intentionally skip it because native file/save dialogs
 * and the signed loopback sidecar are not available to a browser-only runner.
 */
test.describe("core local workflow", () => {
  test.skip(process.env.BIOSTAT_E2E !== "1", "Requires the packaged Electron sidecar and native dialogs.");

  test("imports, approves, analyzes, and exports", async ({ page }) => {
    await page.getByRole("button", { name: "Import Excel" }).click();
    await expect(page.getByText("12 observations")).toBeVisible();
    await page.getByRole("button", { name: "Approve data structure" }).click();
    await page.getByRole("button", { name: "Analysis plan" }).click();
    await page.getByLabel("Approve this plan").check();
    await page.getByRole("button", { name: "Run analysis" }).click();
    await expect(page.getByRole("heading", { name: "Results" })).toBeVisible();
    await page.getByRole("button", { name: "Word report" }).click();
    await page.getByRole("button", { name: "Export Word report" }).click();
  });
});
