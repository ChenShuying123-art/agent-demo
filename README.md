# agent-demo

多个 Agent 学习 demo 的集合仓库（monorepo）。每个 demo 独立放在 `projects/<name>/` 下，共用本仓库的 Git 历史与分支策略。

## Demo 索引

| 项目 | 说明 | 技术栈 | 状态 |
|------|------|--------|------|
| [knowledge-base-qa](./projects/knowledge-base-qa/) | 知识库问答 Agent（RAG MVP）：上传文档 → 两阶段检索（向量召回 + Rerank 重排）→ 三种提示词风格问答 → LLM-as-judge 评测 | Python / FastAPI / Vue 3 + TS + Vite | 开发中 |

## 目录结构

```
agent-demo/
├── README.md
├── .gitignore
└── projects/
    └── knowledge-base-qa/        # 各 demo 的细节见其目录内的文档
        ├── docs/                 # spec.md（设计契约）、tasks.md（任务拆解）
        ├── kbqa/                 # 核心 Python 包（待实现）
        ├── api/                  # FastAPI 接口层（待实现）
        ├── web/                  # Vue 3 前端（待实现）
        └── notebooks/            # 学习用 Notebook（待实现）
```

## 约定

### 目录命名

每个 demo 放在 `projects/` 下，目录名用小写 kebab-case（如 `knowledge-base-qa`）。

### Commit 规范

monorepo 中多个项目共用一个历史，**提交信息必须带项目前缀**（scope），以便一眼区分改动归属：

```
<type>(<scope>): <描述>
```

- `type`：`feat` / `fix` / `docs` / `chore` / `refactor` / `test`
- `scope`：项目名简写。已使用：`kbqa`（knowledge-base-qa）、`repo`（仓库级改动）

示例：

```
chore(repo): 初始化 monorepo 骨架与索引
docs(kbqa): 添加 RAG spec 与任务拆解
feat(kbqa): 实现文档加载与内容哈希去重
```

> 提交时 `git add` 请**指定具体路径**（如 `git add projects/knowledge-base-qa/kbqa/loaders.py`），**不要用 `git add .`**——避免误提交其他项目的半成品或敏感文件。

### 分支策略

- `main`：稳定分支
- 新功能从 `main` 切出 `feat/<scope>-<简述>`，完成后合并回 `main`

### 新增一个 demo 的流程

1. 在 `projects/` 下新建小写 kebab-case 目录
2. 目录内自带 `.gitignore` / `.env.example` / 说明文档
3. 在顶部「Demo 索引」表补一行
4. 按约定用带 scope 前缀的信息提交

## 后续演进

当某个 demo 从「练习」升级为需要独立展示 / 独立部署的作品时，可用：

```
git subtree split --prefix=projects/<name> -b <name>-standalone
```

将其**无损剥离**为独立仓库（Git 历史完整保留）。