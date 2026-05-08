"""
Bug 定位 Agent
==============
职责: 根据 Issue 分析结果 + 混合检索结果，定位最可能出错的代码位置。
输出: Top-K 文件和函数，含定位理由和证据。
"""

import json
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import LLM_MODEL, TOP_K_FILES, TOP_K_FUNCTIONS


class BugLocator:
    """Bug 定位 Agent"""

    def __init__(self):
        self.llm = ChatOllama(model=LLM_MODEL, temperature=0.1)

    def locate(self, issue_analysis: dict, search_results: list[dict]) -> dict:
        """
        根据 Issue 分析和代码检索结果，定位最可能出错的代码位置。

        返回:
            {
                "top_files": [...],
                "top_functions": [...],
                "analysis": "综合分析",
                "recommended_start": "建议先检查的文件"
            }
        """
        keywords = issue_analysis.get("keywords", [])
        summary = issue_analysis.get("summary", "")
        error_type = issue_analysis.get("error_type", "")

        # 按文件去重，保留最高分的 chunk
        file_best = {}
        func_best = {}
        for item in search_results:
            fp = item["file_path"]
            if fp not in file_best or item["score"] > file_best[fp]["score"]:
                file_best[fp] = item

            if item["symbol_type"] in ("function", "method", "test"):
                key = f"{fp}:{item['symbol_name']}"
                if key not in func_best or item["score"] > func_best[key]["score"]:
                    func_best[key] = item

        # 排序
        top_files = sorted(file_best.values(), key=lambda x: x["score"], reverse=True)[:TOP_K_FILES]
        top_functions = sorted(func_best.values(), key=lambda x: x["score"], reverse=True)[:TOP_K_FUNCTIONS]

        # 让 LLM 分析定位结果，给出理由
        analysis = self._analyze_results(summary, error_type, keywords, top_files, top_functions)

        return {
            "top_files": [
                {
                    "file_path": f["file_path"],
                    "score": f["score"],
                    "best_match": f["symbol_name"],
                    "match_type": f["symbol_type"],
                }
                for f in top_files
            ],
            "top_functions": [
                {
                    "file_path": f["file_path"],
                    "symbol_name": f["symbol_name"],
                    "score": f["score"],
                    "line": f["start_line"],
                    "content_preview": f["content"][:200],
                }
                for f in top_functions
            ],
            "analysis": analysis,
            "recommended_start": top_files[0]["file_path"] if top_files else "",
            "search_summary": f"从 {len(search_results)} 个检索结果中定位到 {len(top_files)} 个相关文件、{len(top_functions)} 个相关函数",
        }

    def _analyze_results(self, summary: str, error_type: str, keywords: list[str],
                         top_files: list[dict], top_functions: list[dict]) -> str:
        """让 LLM 分析定位结果，给出可解释的理由"""
        if not top_files:
            return "未找到相关代码文件，建议扩展搜索范围或检查仓库是否包含相关代码。"

        files_text = "\n".join(
            f"- {f['file_path']} (score: {f['score']}, match: {f['symbol_name']})"
            for f in top_files[:5]
        )
        funcs_text = "\n".join(
            f"- {f['file_path']}::{f['symbol_name']} (line {f['start_line']})"
            for f in top_functions[:5]
        )

        prompt = f"""你是一个 Bug 定位专家。根据以下信息，分析最可能的 Bug 位置并给出理由。

Issue 摘要: {summary}
错误类型: {error_type or '未知'}
关键词: {', '.join(keywords[:10])}

检索到的相关文件:
{files_text}

检索到的相关函数:
{funcs_text}

请分析:
1. 哪个文件/函数最可能是 Bug 的源头？为什么？
2. 各候选位置的关联性排序及原因
3. 建议从哪里开始排查

用中文回答，简洁专业，不超过 300 字。"""

        try:
            response = self.llm.invoke([
                SystemMessage(content="你是专业的 Bug 定位专家，输出简洁精准的分析。"),
                HumanMessage(content=prompt),
            ])
            return response.content.strip()
        except Exception:
            return f"基于检索分数，最可能的 Bug 位置在 {top_files[0]['file_path']} (score: {top_files[0]['score']})。"
