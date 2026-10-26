---
name: python-api-basic
version: 1.0.0
description: Python 后端接口基础能力。使用 FastAPI 定义路由与请求校验，统一错误处理，返回清晰的 JSON 响应。
language: python
category: domain
tags: [api, fastapi, backend, 接口]
decision_points:
  web_framework: fastapi
  error_handling: unified_exception_handler
applies_when: 需要 Web 接口、路由、请求参数校验或统一错误响应时
---

# Python 接口基础

- 使用 FastAPI 定义路由，路径以业务名词命名，避免动词堆叠。
- 请求与响应都使用 Pydantic 模型，禁止直接传裸字典。
- 统一异常处理：业务错误返回 `{"error": {"code": ..., "message": ...}}`，不泄露堆栈。
- 所有接口必须有最小冒烟测试，覆盖成功与参数错误两条路径。
