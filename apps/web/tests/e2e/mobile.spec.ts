import { expect, test } from "@playwright/test";
import { uiLogin } from "./helpers";

test("inbox works on a phone screen without horizontal page scroll", async ({ page }) => {
  await uiLogin(page);
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
