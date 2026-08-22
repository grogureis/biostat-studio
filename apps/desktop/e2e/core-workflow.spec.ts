import { _electron as electron, expect, test } from "playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));

test.describe("core local Electron workflow", () => {
  test.skip(process.env.BIOSTAT_E2E !== "1", "Set BIOSTAT_E2E=1 to launch the real Electron test harness.");

  test("imports, explicitly approves, cancels, analyzes, exports bilingually, and reopens", async () => {
    const application = await electron.launch({
      args: [path.join(currentDirectory, "electron-harness.cjs")],
    });
    try {
      const page = await application.firstWindow();
      await page.getByRole("textbox", { name: "Project title" }).fill("Fixture study");
      await page.getByRole("textbox", { name: "Research question" }).fill("Is the outcome different between groups?");
      await page.getByRole("textbox", { name: "Hypothesis" }).fill("The groups have different outcomes.");
      await page.getByRole("textbox", { name: "Outcome variables" }).fill("outcome");
      await page.getByRole("textbox", { name: "Exposure variables" }).fill("group");
      await page.getByRole("button", { name: "Data & variables" }).click();
      await page.getByRole("button", { name: "Import Excel" }).click();
      await expect(page.getByText("12 observations")).toBeVisible();
      await page.getByRole("button", { name: "Approve data structure" }).click();
      await expect(page.getByRole("button", { name: "Data structure approved" })).toBeDisabled();
      await page.getByRole("button", { name: "Analysis plan" }).click();
      await page.getByLabel("Approve this plan").check();
      await page.getByRole("button", { name: "Run analysis" }).click();
      await page.getByRole("button", { name: "Cancel analysis" }).click();
      await expect(page.getByRole("status")).toHaveText("Analysis cancelled. No partial results were accepted.");
      await page.getByRole("button", { name: "Analysis plan" }).click();
      await page.getByRole("button", { name: "Run analysis" }).click();
      await expect(page.getByRole("heading", { name: "Results" })).toBeVisible();
      await page.getByRole("button", { name: "Word report" }).click();
      await page.getByRole("button", { name: "Export Word report" }).click();
      await expect(page.getByRole("status")).toHaveText("Word report saved");
      await page.getByLabel("Report language").selectOption("tr");
      await page.getByRole("button", { name: "Export Word report" }).click();
      await expect(page.getByRole("status")).toHaveText("Word report saved");
      expect(await page.evaluate(() => (window as Window & { biostat: { e2eState(): Promise<{ reportLanguages: string[] }> } }).biostat.e2eState())).toMatchObject({ reportLanguages: ["en", "tr"] });

      await page.reload();
      await page.getByRole("button", { name: "Open project" }).click();
      await expect(page.getByRole("heading", { name: "Results" })).toBeVisible();
      await page.getByRole("button", { name: "Word report" }).click();
      await expect(page.getByRole("button", { name: "Export Word report" })).toBeEnabled();
    } finally {
      await application.close();
    }
  });
});
