"""
Agentic R&D Copilot — 配置文件
===============================
V1 功能: 仓库导入 → 代码索引 → Issue 分析 → Bug 定位
"""

import os

# ============ 路径 ============
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPOS_DIR = os.path.join(DATA_DIR, "repos")       # clone 下来的仓库
INDEXES_DIR = os.path.join(DATA_DIR, "indexes")    # 向量索引 + BM25
LOGS_DIR = os.path.join(DATA_DIR, "logs")

for d in [DATA_DIR, REPOS_DIR, INDEXES_DIR, LOGS_DIR]:
    os.makedirs(d, exist_ok=True)

# ============ LLM ============
LLM_MODEL = "qwen2.5:7b"              # Ollama 对话模型
EMBEDDING_MODEL = "nomic-embed-text"  # Ollama 嵌入模型

# ============ 代码索引 ============
SUPPORTED_EXTENSIONS = [".py"]         # V1 只支持 Python
MAX_FILE_SIZE_KB = 500                # 跳过大文件
CHUNK_OVERLAP_LINES = 3               # 代码块重叠行数

# ============ 混合检索 ============
BM25_WEIGHT = 0.4                     # BM25 权重
EMBEDDING_WEIGHT = 0.4                # 向量相似度权重
STRUCTURAL_WEIGHT = 0.2               # 结构化分数权重（路径、函数名匹配）

# ============ Bug 定位 ============
TOP_K_FILES = 5                       # 返回 Top-K 文件
TOP_K_FUNCTIONS = 5                   # 返回 Top-K 函数

# ============ 服务 ============
HOST = "0.0.0.0"
PORT = 8090
