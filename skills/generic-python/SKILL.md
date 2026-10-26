---
name: generic-python
version: 1.0.0
description: 通用 Python 编码规范。适用于没有命中任何专门技能时的兜底场景。
language: python
category: generic
tags: [python, generic, 通用]
decision_points: {}
applies_when: 没有更匹配的技能时作为兜底
---

# 通用 Python 规范

- 使用标准库优先，第三方依赖必须写进依赖清单。
- 函数保持短小，输入输出用类型标注；错误信息要能定位问题。
- 不吞异常；捕获后要么处理，要么带上下文重新抛出。
- 所有新增文件都要有对应的最小测试。
