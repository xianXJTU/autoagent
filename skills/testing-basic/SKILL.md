---
name: testing-basic
version: 1.0.0
description: Python 项目的测试规范。使用 pytest 编写冒烟、功能、端到端、边界与安全测试，测试先于实现。
language: python
category: domain
tags: [testing, pytest, 测试]
decision_points:
  test_framework: pytest
applies_when: 任何需要编写测试或验收生成物的场景
---

# 测试规范

- 冒烟测试先确认程序能启动，功能与端到端测试再覆盖核心流程。
- 边界至少覆盖空值、极值、错误类型；安全至少覆盖越权与注入。
- 测试必须离线可运行，不依赖外部服务。
- 测试失败时保留原始输出，修复后重跑全套。
