---
name: database-sqlite
version: 1.0.0
description: 使用 SQLite 做本地数据存储，配合 SQLAlchemy 定义数据模型、会话与迁移，保证数据库文件自包含。
language: python
category: domain
tags: [database, sqlite, sqlalchemy, 数据库]
decision_points:
  database: sqlite
  orm: sqlalchemy
applies_when: 需要本地持久化、单文件数据库或简单的数据增删改查时
---

# 本地数据库

- 数据库文件放在项目目录内，路径由配置提供，禁止硬编码绝对路径。
- 使用 SQLAlchemy 2.x 的声明式模型；会话通过统一工厂获取。
- 建表使用迁移脚本，禁止在业务代码里临时建表。
- 时间统一存 UTC；金额使用整数分或 Decimal，禁止浮点。
