# Agentic R&D Copilot V3

> AI 驱动的自动化代码修复平台 — 从 Issue 到 PR，一条命令全自动

## 概述

Agentic R&D Copilot V3 是一个基于 LangGraph 多 Agent 协作的智能研发助手。输入一段自然语言的 Bug 描述，系统自动完成代码检索、Bug 定位、Patch 生成、测试验证和 PR 撰写——把原本需要数小时的排障工作缩短到几分钟。

### V1 vs V3

| 能力 | V1 | V3 |
|------|:--:|:--:|
| Issue 结构化分析 | ✓ | ✓ |
| AST 代码解析 | ✓ | ✓ |
| 混合检索（BM25 + 向量 + 结构） | ✓ | ✓ |
| Bug 定位 + Top-K 文件/函数 | ✓ | ✓ |
| Patch 生成（unified diff） | ✗ | ✓ |
| 测试验证（pytest + ruff + mypy） | ✗ | ✓ |
| PR 自动撰写 | ✗ | ✓ |
| Benchmark 评测 | ✗ | ✓ |
| 本地仓库导入 | ✗ | ✓ |

## 架构

```
┌──────────────────────────────────────────────────────────┐
│                     Web UI (localhost:8090)               │
└──────────────────────────┬───────────────────────────────┘
                           │ REST API
┌──────────────────────────▼───────────────────────────────┐
│                  FastAPI Server (main.py)                 │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│           LangGraph 6-Agent Workflow (workflow.py)        │
│                                                           │
│  ① IssueAnalyzer  →  ② HybridSearch  →  ③ BugLocator    │
│         │                                         │       │
│         │              V1 模式 ◄──────────────────┘       │
│         │                                                 │
│         ▼                                                 │
│  ④ PatchGenerator  →  ⑤ TestRunner  →  ⑥ PRAgent (V3)   │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│             混合检索引擎 (repo_indexer.py)                 │
│                                                           │
│   Python AST ──→ ChromaDB 向量  ──→  融合分数            │
│              ──→ BM25 + jieba  ──→  (0.4+0.4+0.2)        │
│              ──→ 路径/函数名匹配                         │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│            Ollama 本地 LLM（零外部 API 依赖）              │
│     对话: qwen3.5:4b     │    嵌入: nomic-embed-text      │
└──────────────────────────────────────────────────────────┘
```

## 6 Agent 工作流

| 步骤 | Agent | 职责 | 输出 |
|:----:|-------|------|------|
| ① | IssueAnalyzer | 将自然语言 Issue 结构化为类型、关键词、严重程度 | JSON 分析报告 |
| ② | RepoIndexer.hybrid_search | BM25 + 向量 + 结构三维度混合检索 | 排序后的代码块列表 |
| ③ | BugLocator | 根据检索结果定位最可能的 Bug 位置，给出可解释的理由 | Top-K 文件 + 函数 + 分析文本 |
| ④ | PatchGenerator | 生成最小修改 unified diff，标注风险等级和回滚方案 | diff + 风险说明 |
| ⑤ | TestRunner | 在本地执行 pytest / ruff / mypy 三合一验证 | 测试报告 |
| ⑥ | PRAgent | 结合全链路上下文撰写 PR 标题、描述、checklist | PR 完整内容 |

## 环境要求

| 组件 | 用途 | 安装 |
|------|------|------|
| Python 3.11+ | 运行环境 | [python.org](https://python.org) |
| Ollama | 本地 LLM 推理 | [ollama.com](https://ollama.com) |
| Git | GitHub 仓库 clone | [git-scm.com](https://git-scm.com) |

## 快速开始

### 1. 启动 Ollama 并拉取模型

```bash
ollama pull qwen3.5:4b        # 对话模型（~3.4G）
ollama pull nomic-embed-text   # 嵌入模型（~274M）
```

### 2. 安装 Python 依赖

```bash
cd agentic-rd-copilot
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # macOS / Linux

pip install fastapi uvicorn pydantic chromadb rank-bm25 jieba \
            ollama langchain langchain-ollama langgraph \
            pytest ruff mypy --break-system-packages
```

### 3. 启动服务

```bash
cd backend
python main.py
```

出现以下输出表示启动成功：

```
==================================================
  Agentic R&D Copilot v1.0
  访问: http://localhost:8090
==================================================
```

### 4. 在浏览器中操作

打开 `http://localhost:8090`，按顺序操作：

1. 导入仓库（GitHub URL 或本地路径）
2. 建立索引（自动 AST 解析 + 向量化 + BM25）
3. 输入 Issue 描述
4. 点击「V1 定位」或「V3 全链路」查看结果

## API 参考

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/repos/import` | 从 GitHub clone 仓库 |
| `POST` | `/api/repos/import-local` | 导入本地文件夹 |
| `POST` | `/api/repos/{id}/index` | 为仓库建立索引 |
| `POST` | `/api/issues/analyze` | V1 Bug 定位 |
| `POST` | `/api/issues/analyze-full` | V3 全链路（定位 + Patch + 验证 + PR） |
| `GET` | `/api/tasks/{id}` | 查询异步任务结果 |
| `POST` | `/api/eval/run` | 运行 Benchmark 评测 |
| `GET` | `/api/repos/{id}/stats` | 索引统计 |
| `GET` | `/api/health` | 健康检查 |

### curl 示例

```bash
# 导入仓库
curl -X POST http://localhost:8090/api/repos/import \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/psf/requests","branch":"main"}'

# 建立索引
curl -X POST http://localhost:8090/api/repos/<repo_id>/index

# V1 Bug 定位
curl -X POST http://localhost:8090/api/issues/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo_id":"<repo_id>","issue_text":"POST request body lost after 302 redirect"}'

# V3 全链路
curl -X POST http://localhost:8090/api/issues/analyze-full \
  -H "Content-Type: application/json" \
  -d '{"repo_id":"<repo_id>","issue_text":"timeout not respected in session.get"}'

# 查看结果
curl http://localhost:8090/api/tasks/<task_id>
```

## 项目结构

```
agentic-rd-copilot/
├── backend/
│   ├── main.py                 # FastAPI 服务入口
│   ├── config.py               # 全局配置（模型、路径、检索权重）
│   ├── workflow.py             # LangGraph 多 Agent 状态机
│   ├── agents/
│   │   ├── issue_analyzer.py   # ① Issue 结构化分析
│   │   ├── bug_locator.py      # ③ Bug 定位 + 理由生成
│   │   ├── patch_generator.py  # ④ unified diff 生成
│   │   └── pr_agent.py         # ⑥ PR 内容撰写
│   ├── indexer/
│   │   ├── repo_indexer.py     # 仓库导入 + 混合检索引擎
│   │   └── ast_parser.py       # Python AST 解析器
│   ├── tools/
│   │   └── test_runner.py      # ⑤ pytest / ruff / mypy 执行器
│   └── eval/
│       └── benchmark.py        # Top-K 准确率 + MRR 评测
├── frontend/
│   └── index.html              # Web 操作界面
├── data/
│   ├── repos/                  # clone 的仓库
│   ├── indexes/                # ChromaDB 向量 + BM25 索引
│   └── logs/                   # 运行日志
└── .venv/                      # Python 虚拟环境
```

## 配置说明

`backend/config.py` 中的关键参数：

```python
# ── LLM ──
LLM_MODEL = "qwen3.5:4b"            # 对话模型（Ollama）
EMBEDDING_MODEL = "nomic-embed-text" # 嵌入模型（Ollama）

# ── 代码索引 ──
SUPPORTED_EXTENSIONS = [".py"]       # 当前仅支持 Python
MAX_FILE_SIZE_KB = 500               # 跳过超大文件
CHUNK_OVERLAP_LINES = 3              # 代码块重叠行数

# ── 混合检索权重 ──
BM25_WEIGHT = 0.4                    # BM25 关键词匹配
EMBEDDING_WEIGHT = 0.4               # 向量语义匹配
STRUCTURAL_WEIGHT = 0.2              # 路径/函数名结构匹配

# ── Bug 定位 ──
TOP_K_FILES = 5                      # 返回 Top-K 文件
TOP_K_FUNCTIONS = 5                  # 返回 Top-K 函数

# ── 服务 ──
HOST = "0.0.0.0"
PORT = 8090
```

## Benchmark 评测

内置评测模块，支持 Bug 定位准确性量化：

```python
from eval.benchmark import Benchmark

benchmark = Benchmark()

cases = [
    {"issue_text": "POST redirect loses body", "ground_truth_file": "models.py"},
    {"issue_text": "timeout not working",      "ground_truth_file": "adapters.py"},
]

metrics = benchmark.run_benchmark(cases, run_analysis)
# → {top1_accuracy: 0.5, top3_accuracy: 1.0, top5_accuracy: 1.0, mrr: 0.75}
```

## 技术栈

| 模块 | 技术选型 |
|------|----------|
| Agent 编排 | LangGraph StateGraph |
| 代码解析 | Python AST（标准库 ast 模块） |
| 向量检索 | ChromaDB + Ollama Embeddings |
| 关键词检索 | BM25Okapi (rank-bm25) + jieba 分词 |
| 混合检索 | BM25(0.4) + 向量(0.4) + 结构(0.2) 加权融合 |
| LLM 推理 | Ollama 本地部署 |
| 对话模型 | qwen3.5:4b |
| 嵌入模型 | nomic-embed-text |
| Web 框架 | FastAPI + Pydantic |
| 前端 | 原生 HTML/CSS/JS（零框架依赖） |
| 代码验证 | pytest + ruff + mypy |
| Python 最低版本 | 3.11 |

## FAQ

**Q: 启动时刷 LangChainPendingDeprecationWarning？**

无害，main.py 已过滤该警告，不影响功能。

**Q: `ollama serve` 报 "address already in use"？**

Ollama 已经在后台运行了，不需要手动启动。用 `ollama list` 确认。

**Q: 前端显示"前端页面未找到"？**

确保启动时的 working directory 是项目根目录（PyCharm: Run → Edit Configurations → Working directory）。

**Q: 如何换用其他模型？**

修改 `config.py` 中的 `LLM_MODEL`，例如改为 `deepseek-ocr:latest`，然后重启服务。

**Q: 索引很慢？**

向量嵌入需要时间，文件越多越慢。可以用 `MAX_FILE_SIZE_KB` 限制，或只索引核心源码目录。

## License

MIT
