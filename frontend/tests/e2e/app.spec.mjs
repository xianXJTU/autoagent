import { expect, test } from "@playwright/test";

test("首页与新建项目表单可加载", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("autoagent")).toBeVisible();
  await expect(page.getByText("把一句话变成能运行的软件")).toBeVisible();
  await expect(page.getByPlaceholder("项目名称")).toBeVisible();
  await expect(page.getByPlaceholder("一句话说出你的需求")).toBeVisible();
  await expect(page.getByRole("button", { name: "新建项目" })).toBeVisible();
});

test("问题以独立卡片呈现，可逐题修改", async ({ page }) => {
  const detail = {
    id: "demo",
    name: "卡片演示",
    status: "对齐中",
    run_id: null,
    run_status: "对齐中",
    messages: [
      {
        id: "m1",
        role: "user",
        agent_id: null,
        content: "做个家庭记账工具",
        meta: {},
        created_at: ""
      },
      {
        id: "m2",
        role: "planner",
        agent_id: "planner",
        content: "第 1 轮问题",
        meta: {
          questions: {
            questions: [
              {
                question: "这个工具主要给谁用？",
                recommendation: "只给你自己用",
                reason: "一个人使用不需要登录和权限，能更快做出来。",
                options: []
              },
              {
                question: "账单要导出吗？",
                recommendation: "导出 CSV",
                reason: "方便留档和用表格查看。",
                options: []
              }
            ]
          }
        },
        created_at: ""
      }
    ],
    readme: null,
    modules: []
  };
  let posted = null;
  await page.route("**/api/projects", (route) =>
    route.fulfill({
      json: [
        { id: "demo", name: "卡片演示", status: "对齐中", updated_at: "" }
      ]
    })
  );
  await page.route("**/api/projects/demo", (route) =>
    route.fulfill({ json: detail })
  );
  await page.route("**/api/projects/demo/messages/stream", async (route) => {
    posted = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
      body:
        'event: thinking\ndata: {"text":"先想一想"}\n\n' +
        'event: result\ndata: {"action":"questions"}\n\n'
    });
  });

  await page.goto("/");
  await page.getByText("卡片演示").first().click();
  await expect(page.getByRole("button", { name: "采用推荐" })).toHaveCount(2);
  const inputs = page.locator(".question-input");
  await expect(inputs).toHaveCount(2);
  await inputs.first().fill("只给家里人用");
  await page.getByRole("button", { name: "提交本轮回答" }).click();
  await expect
    .poll(() => posted?.text ?? "")
    .toContain("只给家里人用");
  expect(posted?.text ?? "").toContain("导出 CSV");
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
