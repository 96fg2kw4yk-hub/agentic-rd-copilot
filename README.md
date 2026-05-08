# Agentic R&D Copilot

面向代码仓库理解、Issue 定位与自动修复的多智能体研发协作平台。

## V1 已完成功能

- GitHub 仓库导入
- AST 代码解析（函数、类、import、测试识别）
- 混合检索（BM25 + 向量 + 结构化分数）
- Issue 结构化分析 Agent
- Bug 定位 Agent
- LangGraph 多 Agent 编排
- FastAPI 后端 + Web 前端

## 项目结构

```
agentic-rd-copilot/
├── backend/
│   ├── main.py              # FastAPI 服务
│   ├── config.py            # 配置
│   ├── workflow.py          # LangGraph 工作流
│   ├── agents/
│   │   ├── issue_analyzer.py  # Issue 分析 Agent
│   │   └── bug_locator.py     # Bug 定位 Agent
│   └── indexer/
│       ├── ast_parser.py      # AST 代码解析器
│       └── repo_indexer.py    # 仓库索引 + 混合检索
├── frontend/
│   └── index.html           # Web 前端
├── data/                    # 仓库、索引、日志
├── requirements.txt
└── README.md
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt --break-system-packages

# 2. 安装 Ollama 并拉模型
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

# 3. 启动服务
cd backend
python main.py

# 4. 浏览器打开 http://localhost:8090
```

## 使用流程

1. 输入 GitHub 仓库地址 → 导入仓库
2. 建立代码索引（AST 解析 + 向量 + BM25）
3. 输入 Issue 描述 → 自动定位 Bug 代码位置

## 核心技术

| 模块 | 技术 |
|------|------|
| Agent 编排 | LangGraph |
| 代码解析 | Python AST |
| 向量检索 | ChromaDB + Ollama Embedding |
| 关键词检索 | BM25 + jieba |
| 混合检索 | BM25(0.4) + 向量(0.4) + 结构化(0.2) |
| LLM | Ollama + qwen2.5:7b |
| Web | FastAPI + 原生 HTML/CSS/JS |
