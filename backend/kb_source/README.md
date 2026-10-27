# 工单知识库数据源（kb_source）

本目录是内部 IT 知识库的 **Markdown 原文**，供 RAG 入库（切分 → Embedding → Milvus）使用，也可同步到业务库文章表。

## 目录与工单类别

子目录名与系统工单 `category` 一致：

| 目录 | 类别 | 说明 |
|------|------|------|
| `account/` | account | 账号、密码、邮箱、入职离职等 |
| `device/` | device | 电脑、外设、打印机等 |
| `network/` | network | 办公网、VPN、DNS 等 |
| `permission/` | permission | 系统权限、共享目录、角色变更等 |

## 和 Skill 的区别

| | `kb_source/`（本目录） | `src/agent/skills/` |
|--|------------------------|---------------------|
| 内容 | 可多篇、可较长的处理手册 | 短 SOP，按类别懒加载 |
| 用途 | 混合检索（向量+BM25→RRF→重排），给 `search_kb` | 注入「本单 Skill」提示 |
| 更新 | 增删改 md 后重新入库 | 改 md 即可，随图加载 |

## 入库建议

1. 遍历本目录下各类别 `.md`，或在知识库页上传 PDF / DOCX / MD / 图片（`POST /api/kb/ingest`，先「已受理」）
2. 按标题/段落递归切分（可带 overlap）；图片勾选 OCR 时走百炼视觉抽文字
3. 调用 embedding 写入 Milvus，元数据带上 `category`；块 id 为 `article_id * 10000 + i`
4. 正文同步进业务库 `kb_article`，任务状态见 `kb_ingest_job`

## 维护

- 可直接增删改各分类下的 md，再跑项目里的知识库同步脚本/流程
- 勿把密钥、真实员工隐私写进示例手册；当前为演示用模拟内容
