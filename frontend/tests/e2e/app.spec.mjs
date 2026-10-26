import { expect, test } from "@playwright/test";

test("首页与新建项目表单可加载", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("autoagent")).toBeVisible();
  await expect(page.getByText("把一句话变成能运行的软件")).toBeVisible();
  await expect(page.getByPlaceholder("项目名称")).toBeVisible();
  await expect(page.getByPlaceholder("一句话说出你的需求")).toBeVisible();
  await expect(page.getByRole("button", { name: "新建项目" })).toBeVisible();
});

test("可以彻底删除项目", async ({ page, request }) => {
  const name = `删除测试-${Date.now()}`;
  const created = await request.post("/api/projects", {
    data: { name, requirement: "删除测试" }
  });
  expect(created.ok()).toBeTruthy();
  const { project_id: projectId } = await created.json();
  try {
    await page.goto("/");
    await expect(page.getByText(name)).toBeVisible();
    await page.getByText(name).first().click();
    await page.getByRole("button", { name: "删除项目", exact: true }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("彻底删除（同时删除匿名运行轨迹）").check();
    await dialog.getByRole("button", { name: "确认删除" }).click();

    await expect(page.getByText(name)).toHaveCount(0);
    const check = await request.get(`/api/projects/${projectId}`);
    expect(check.status()).toBe(404);
  } finally {
    await request
      .delete(`/api/projects/${projectId}?keep_traces=false`)
      .catch(() => undefined);
  }
});
