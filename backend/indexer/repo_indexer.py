"""
仓库索引器
==========
负责: clone 仓库 → 扫描文件 → AST 解析 → 向量索引 → BM25 索引

这是整个系统的"地基"，后续所有 Agent 都依赖这些索引。
"""

import os
import subprocess
import hashlib
import pickle
import json
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings
from rank_bm25 import BM25Okapi
import jieba

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import *
from indexer.ast_parser import ASTParser, CodeChunk


class RepoIndexer:
    """仓库索引器：clone + 扫描 + 索引一站式"""

    def __init__(self):
        self.ast_parser = ASTParser()
        self.embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)

        # ChromaDB 客户端
        self.chroma_client = chromadb.PersistentClient(
            path=os.path.join(INDEXES_DIR, "chroma"),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # 内存中的索引缓存
        self.chunks: list[CodeChunk] = []
        self.bm25: Optional[BM25Okapi] = None
        self.bm25_chunks: list[CodeChunk] = []
        self.current_repo_id: str = ""
        self.vector_store = None  # Chroma wrapper，确保查询和索引用同一嵌入模型

    # ========== 仓库导入 ==========

    def import_local(self, local_path: str) -> dict:
        """导入本地文件夹（不需要 clone）"""
        local_path = os.path.abspath(local_path)
        if not os.path.isdir(local_path):
            return {"status": "error", "message": "文件夹不存在"}

        folder_name = os.path.basename(local_path)
        repo_id = hashlib.md5(local_path.encode()).hexdigest()[:12]
        result = {
            "repo_id": repo_id,
            "repo_name": folder_name,
            "local_path": local_path,
            "status": "local_imported",
            "message": f"已导入本地文件夹: {local_path}",
        }
        return result

    def import_repo(self, repo_url: str, branch: str = "main") -> dict:
        """
        Clone 一个 GitHub 仓库到本地。
        返回 repo_id 和仓库信息。
        """
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        repo_id = hashlib.md5(f"{repo_url}:{branch}".encode()).hexdigest()[:12]
        local_path = os.path.join(REPOS_DIR, f"{repo_name}-{repo_id}")

        result = {"repo_id": repo_id, "repo_name": repo_name, "local_path": local_path}

        # 如果已存在，直接返回
        if os.path.exists(local_path):
            result["status"] = "already_exists"
            result["message"] = "仓库已存在"
            return result

        # Clone
        try:
            cmd = ["git", "clone", "--depth", "1", "--branch", branch, repo_url, local_path]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if proc.returncode == 0:
                result["status"] = "cloned"
                result["message"] = "克隆成功"
            else:
                result["status"] = "error"
                result["message"] = proc.stderr[:200]
        except subprocess.TimeoutExpired:
            result["status"] = "error"
            result["message"] = "克隆超时（超过 120 秒）"
        except FileNotFoundError:
            result["status"] = "error"
            result["message"] = "未找到 git 命令，请安装 Git"

        return result

    # ========== 代码扫描与解析 ==========

    def scan_and_parse(self, repo_id: str, local_path: str) -> dict:
        """
        扫描仓库中所有 Python 文件，用 AST 解析并生成 chunk 列表。
        """
        self.current_repo_id = repo_id
        self.chunks = []

        py_files = list(Path(local_path).rglob("*.py"))
        # 排除常见的非代码目录
        exclude_dirs = {"venv", ".venv", "__pycache__", "node_modules", ".git",
                         "env", ".env", "site-packages", "dist", "build", ".tox"}
        py_files = [f for f in py_files if not any(d in f.parts for d in exclude_dirs)]

        # 过滤大文件
        valid_files = []
        for f in py_files:
            try:
                size_kb = f.stat().st_size / 1024
                if size_kb <= MAX_FILE_SIZE_KB:
                    valid_files.append(f)
            except OSError:
                pass

        stats = {"total_files": len(py_files), "valid_files": len(valid_files),
                 "total_functions": 0, "total_classes": 0, "total_chunks": 0}

        for file_path in valid_files:
            try:
                source = file_path.read_text(encoding="utf-8", errors="ignore")
                file_chunks = self.ast_parser.parse_file(repo_id, str(file_path), source)
                self.chunks.extend(file_chunks)

                for c in file_chunks:
                    if c.symbol_type in ("function", "method"):
                        stats["total_functions"] += 1
                    elif c.symbol_type == "class":
                        stats["total_classes"] += 1
                    elif c.symbol_type == "test":
                        stats["total_functions"] += 1
            except Exception as e:
                print(f"  [跳过] {file_path}: {e}")

        stats["total_chunks"] = len(self.chunks)
        stats["repo_id"] = repo_id
        return stats

    # ========== 向量索引 ==========

    def build_vector_index(self) -> dict:
        """为所有 chunk 建立 ChromaDB 向量索引"""
        if not self.chunks:
            return {"error": "没有 chunk，请先执行 scan_and_parse"}

        repo_id = self.current_repo_id
        persist_dir = os.path.join(INDEXES_DIR, "chroma", f"repo_{repo_id}")

        # 删除旧索引
        import shutil
        if os.path.exists(persist_dir):
            shutil.rmtree(persist_dir)

        # 转为 LangChain Documents
        from langchain_core.documents import Document
        docs = []
        for c in self.chunks:
            docs.append(Document(
                page_content=self._chunk_to_text(c),
                metadata={
                    "chunk_id": c.chunk_id,
                    "file_path": c.file_path,
                    "symbol_type": c.symbol_type,
                    "symbol_name": c.symbol_name,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                }
            ))

        # 用 Ollama 嵌入模型创建向量库
        print(f"  [index] 正在嵌入 {len(docs)} 个文档到 {persist_dir}...")
        self.vector_store = Chroma.from_documents(
            documents=docs,
            embedding=self.embeddings,
            persist_directory=persist_dir,
        )
        print(f"  [index] 向量索引完成")

        return {
            "repo_id": repo_id,
            "chunk_count": len(docs),
            "status": "indexed",
        }

    # ========== BM25 索引 ==========

    def build_bm25_index(self):
        """为所有 chunk 建立 BM25 关键词索引"""
        if not self.chunks:
            return

        # 用 jieba 分词构建 BM25
        tokenized = []
        self.bm25_chunks = []

        for chunk in self.chunks:
            text = self._chunk_to_text(chunk)
            tokens = list(jieba.cut(text))
            tokenized.append(tokens)
            self.bm25_chunks.append(chunk)

        self.bm25 = BM25Okapi(tokenized)

        # 持久化
        bm25_path = os.path.join(INDEXES_DIR, f"bm25_{self.current_repo_id}.pkl")
        with open(bm25_path, "wb") as f:
            pickle.dump({"chunks": self.bm25_chunks, "bm25": self.bm25}, f)

    # ========== 混合检索 ==========

    def _load_vector_store(self, repo_id: str):
        """从磁盘加载向量存储"""
        persist_dir = os.path.join(INDEXES_DIR, "chroma", f"repo_{repo_id}")
        if not os.path.exists(persist_dir):
            print(f"  [hybrid] 向量库路径不存在: {persist_dir}")
            return None
        vs = Chroma(
            embedding_function=self.embeddings,
            persist_directory=persist_dir,
        )
        print(f"  [hybrid] 从磁盘加载向量库: {persist_dir}")
        return vs

    def _load_bm25(self, repo_id: str):
        """从磁盘加载 BM25"""
        bm25_path = os.path.join(INDEXES_DIR, f"bm25_{repo_id}.pkl")
        if not os.path.exists(bm25_path):
            print(f"  [hybrid] BM25 路径不存在: {bm25_path}")
            return None, []
        with open(bm25_path, "rb") as f:
            data = pickle.load(f)
            print(f"  [hybrid] 从磁盘加载 BM25: {len(data['chunks'])} 条")
            return data["bm25"], data["chunks"]

    def hybrid_search(self, query: str, repo_id: str = "", top_k: int = TOP_K_FILES) -> list[dict]:
        """
        混合检索：BM25 + 向量 + 结构化分数
        """
        repo_id = repo_id or self.current_repo_id
        print(f"  [hybrid] 用 repo_id={repo_id!r} 检索: {query[:60]}...")

        # 1. 向量检索
        vs = self._load_vector_store(repo_id)
        vec_docs = []
        if vs:
            try:
                vec_docs = vs.similarity_search_with_score(query, k=top_k * 2)
                print(f"  [hybrid] 向量检索: {len(vec_docs)} 条")
            except Exception as e:
                print(f"  [hybrid] 向量检索异常: {e}")

        # 2. BM25 检索
        bm25, bm25_chunks = self._load_bm25(repo_id)
        bm25_scores = {}
        if bm25 and bm25_chunks:
            query_tokens = list(jieba.cut(query))
            bm25_raw = bm25.get_scores(query_tokens)
            for i, score in enumerate(bm25_raw):
                chunk_id = bm25_chunks[i].chunk_id
                bm25_scores[chunk_id] = score
            print(f"  [hybrid] BM25 检索: {len(bm25_scores)} 条, 非零={sum(1 for s in bm25_scores.values() if s > 0)}")
        else:
            print(f"  [hybrid] BM25 未就绪")

        # 3. 合并分数
        combined = {}

        # 向量分数
        vec_max_score = max((s for _, s in vec_docs), default=1.0)
        for doc, score in vec_docs:
            chunk_id = doc.metadata.get("chunk_id", "")
            norm_score = score / vec_max_score if vec_max_score > 0 else 0
            combined[chunk_id] = {
                "vec_score": norm_score, "bm25_score": 0, "final_score": 0,
                "doc": doc,
            }

        # BM25 分数
        bm25_max = max(bm25_scores.values()) if bm25_scores else 1.0
        for chunk_id, score in bm25_scores.items():
            norm = score / bm25_max if bm25_max > 0 else 0
            if chunk_id in combined:
                combined[chunk_id]["bm25_score"] = norm
            else:
                # BM25 命中但向量未命中，从 bm25_chunks 补信息
                for c in self.bm25_chunks:
                    if c.chunk_id == chunk_id:
                        from langchain_core.documents import Document
                        combined[chunk_id] = {
                            "vec_score": 0, "bm25_score": norm, "final_score": 0,
                            "doc": Document(page_content=self._chunk_to_text(c), metadata={
                                "chunk_id": c.chunk_id, "file_path": c.file_path,
                                "symbol_type": c.symbol_type, "symbol_name": c.symbol_name,
                                "start_line": c.start_line, "end_line": c.end_line,
                            }),
                        }
                        break

        # 结构化分数
        query_lower = query.lower()
        for chunk_id, info in combined.items():
            doc = info["doc"]
            fp = doc.metadata.get("file_path", "")
            sn = doc.metadata.get("symbol_name", "")
            st = doc.metadata.get("symbol_type", "")
            structural = 0.0
            for word in query_lower.split():
                if word in sn.lower(): structural += 0.3
                if word in fp.lower(): structural += 0.2
            if "test" in fp.lower(): structural += 0.1
            info["structural_score"] = min(structural, 0.5)
            info["final_score"] = (
                BM25_WEIGHT * info["bm25_score"] +
                EMBEDDING_WEIGHT * info["vec_score"] +
                STRUCTURAL_WEIGHT * info["structural_score"]
            )

        # 排序返回
        sorted_items = sorted(combined.values(), key=lambda x: x["final_score"], reverse=True)
        results = []
        for item in sorted_items[:top_k]:
            doc = item["doc"]
            results.append({
                "chunk_id": doc.metadata.get("chunk_id", ""),
                "file_path": doc.metadata.get("file_path", ""),
                "symbol_type": doc.metadata.get("symbol_type", ""),
                "symbol_name": doc.metadata.get("symbol_name", ""),
                "start_line": doc.metadata.get("start_line", 0),
                "end_line": doc.metadata.get("end_line", 0),
                "content": doc.page_content[:500],
                "score": round(item["final_score"], 3),
                "vec_score": round(item["vec_score"], 3),
                "bm25_score": round(item["bm25_score"], 3),
                "structural_score": round(item["structural_score"], 3),
            })
        return results

    # ========== 辅助方法 ==========

    def _chunk_to_text(self, chunk: CodeChunk) -> str:
        """将 CodeChunk 转为可索引的文本"""
        parts = [
            f"[{chunk.symbol_type}] {chunk.symbol_name}",
            f"文件: {chunk.file_path}",
        ]
        if chunk.summary:
            parts.append(f"摘要: {chunk.summary}")
        if chunk.docstring:
            parts.append(f"文档: {chunk.docstring}")
        if chunk.imports:
            parts.append(f"依赖: {', '.join(chunk.imports[:10])}")
        if chunk.params:
            parts.append(f"参数: {', '.join(chunk.params)}")
        parts.append(f"代码:\n{chunk.content[:1000]}")
        return "\n".join(parts)

    def get_stats(self) -> dict:
        """获取当前索引统计"""
        return {
            "repo_id": self.current_repo_id,
            "total_chunks": len(self.chunks),
            "has_bm25": self.bm25 is not None,
            "files": len(set(c.file_path for c in self.chunks)),
            "functions": len([c for c in self.chunks if c.symbol_type in ("function", "method")]),
            "classes": len([c for c in self.chunks if c.symbol_type == "class"]),
            "tests": len([c for c in self.chunks if c.symbol_type == "test"]),
        }
