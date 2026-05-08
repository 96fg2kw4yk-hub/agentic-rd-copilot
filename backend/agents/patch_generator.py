"""
Patch 生成 Agent
================
职责: 根据 Bug 定位结果生成最小修改 diff。
约束:
  1. 只能修改 Top-K 文件
  2. 必须输出 unified diff 格式
  3. 必须说明修改原因和风险
  4. 不允许大规模重构
"""

import json
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import LLM_MODEL


class PatchGenerator:
    """代码 Patch 生成 Agent"""

    def __init__(self):
        self.llm = ChatOllama(model=LLM_MODEL, temperature=0.1)

    def generate(self, issue_analysis: dict, location: dict) -> dict:
        """
        根据 Issue 分析和 Bug 定位结果，生成最小修改 Patch。

        返回:
            {
                "patch_id": str,
                "diff": str,           # unified diff 格式
                "explanation": str,    # 修改原因
                "risk_level": "low|medium|high",
                "risk_notes": str,     # 风险说明
                "rollback_plan": str,  # 回滚方案
                "files_modified": [str],
            }
        """
        summary = issue_analysis.get("summary", "")
        error_type = issue_analysis.get("error_type", "")
        keywords = issue_analysis.get("keywords", [])

        top_files = location.get("top_files", [])
        top_functions = location.get("top_functions", [])

        if not top_files:
            return {"error": "未找到可修改的文件"}

        # 构建代码上下文
        context_parts = []
        for func in top_functions[:3]:
            context_parts.append(
                f"### {func['file_path']}::{func['symbol_name']} (行{func['line']})\n"
                f"```python\n{func['content_preview']}\n```"
            )

        # 主文件
        primary_file = top_files[0]["file_path"] if top_files else ""
        context = "\n\n".join(context_parts) if context_parts else "代码上下文不可用"

        prompt = f"""你是一个资深软件工程师，请为以下 Bug 生成最小修改 Patch。

## Issue 信息
- 摘要: {summary}
- 错误类型: {error_type or '未知'}
- 关键词: {', '.join(keywords[:8])}

## Bug 定位结果
- 主要问题文件: {primary_file}
- 相关函数:
{context[:3000]}

## 要求
1. 只修改上述文件，不要修改其他文件
2. 生成最小修改，不要大规模重构
3. 以 unified diff 格式输出修改

请以 JSON 格式返回:
{{
    "files_modified": ["文件路径"],
    "diff": "完整的 unified diff（包含 ---/+++ 头部）",
    "explanation": "用中文解释修改了什么、为什么这样改",
    "risk_level": "low|medium|high",
    "risk_notes": "潜在风险说明",
    "rollback_plan": "如何回滚",
    "test_suggestion": "建议增加的测试用例"
}}

只返回 JSON，不要其他文字。"""

        try:
            response = self.llm.invoke([
                SystemMessage(content="你是资深软件工程师，精通代码修复。输出精确 JSON。"),
                HumanMessage(content=prompt),
            ])
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text)
            result["patch_id"] = f"patch_{os.urandom(4).hex()}"
            return result
        except Exception as e:
            return {
                "patch_id": f"patch_{os.urandom(4).hex()}",
                "error": str(e),
                "files_modified": [f["file_path"] for f in top_files[:2]],
                "diff": self._generate_fallback_diff(top_files, top_functions),
                "explanation": f"基于 Bug 定位结果，建议检查 {primary_file}",
                "risk_level": "medium",
                "risk_notes": "自动生成，需人工审查",
                "rollback_plan": f"git checkout -- {primary_file}",
            }

    def _generate_fallback_diff(self, top_files: list, top_functions: list) -> str:
        """当 LLM 不可用时，生成基础 diff 框架"""
        if not top_files:
            return ""
        lines = []
        for f in top_files[:2]:
            lines.append(f"--- a/{f['file_path']}")
            lines.append(f"+++ b/{f['file_path']}")
            lines.append(f"@@ -1,1 +1,1 @@")
            lines.append(f" // 建议人工检查此处代码")
            lines.append("")
        return "\n".join(lines)
