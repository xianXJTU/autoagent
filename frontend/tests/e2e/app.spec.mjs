import { expect, test } from "@playwright/test";

test("首页与新建项目表单可加载", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("autoagent")).toBeVisible();
  await expect(page.getByText("把一句话变成能运行的软件")).toBeVisible();
  await expect(page.getByPlaceholder("项目名称")).toBeVisible();
  await expect(page.getByPlaceholder("一句话说出你的需求")).toBeVisible();
  await expect(page.getByRole("button", { name: "新建项目" })).toBeVisible();
});
