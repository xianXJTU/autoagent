---
name: python-frontend-basic
version: 1.0.0
description: 零构建的网页界面。使用原生 HTML、CSS 与 ES 模块，静态资源全部本地化，不依赖任何外部 CDN。
language: python
category: domain
tags: [frontend, html, css, 页面]
decision_points:
  frontend: vanilla_html
  assets: local_only
applies_when: 需要生成网页界面、表单、列表、简单图表或页面导航时
---

# 零构建网页界面

- 页面放在 `templates/` 或 `static/` 下，由后端直接托管。
- 禁止引用外部字体、样式库与脚本；所有资源随项目交付。
- 交互用原生 ES 模块；请求统一封装，错误提示必须可见。
- 表单必须做前端最小校验，服务端仍要再校验一次。
