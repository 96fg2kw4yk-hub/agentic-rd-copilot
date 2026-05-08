"""
PR Agent
========
职责: 根据 Patch 和验证结果生成完整的 PR 内容。
输出: PR 标题、描述、测试结果、风险说明、回滚方案。
"""

import json
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import LLM_MODEL


class PRAgent:
    """PR 生成 Agent"""

    def __init__(self):
        self.llm = ChatOllama(model=LLM_MODEL, temperature=0.2)

    def generate(self, issue_analysis: dict, location: dict, patch: dict,
                 verification: dict) -> dict:
        """
        生成完整的 PR 内容。

        返回:
            {
                "title": str,
                "description": str,
                "summary": str,
                "test_results": str,
                "risk_assessment": str,
                "rollback": str,
                "checklist": [str],
            }
        """
        summary = issue_analysis.get("summary", "")
        issue_type = issue_analysis.get("issue_type", "bug")
        severity = issue_analysis.get("severity", "medium")

        patch_explanation = patch.get("explanation", "")
        risk_level = patch.get("risk_level", "medium")
        risk_notes = patch.get("risk_notes", "")
        rollback = patch.get("rollback_plan", "")
        files = patch.get("files_modified", [])

        overall = verification.get("overall", "unknown")
        pytest_result = verification.get("pytest", {}).get("status", "skipped")
        ruff_result = verification.get("ruff", {}).get("status", "skipped")
        mypy_result = verification.get("mypy", {}).get("status", "skipped")

        prompt = f"""你是一个专业的软件工程师，请为以下代码修复生成 Pull Request 内容。

## Issue 信息
- 类型: {issue_type}
- 严重程度: {severity}
- 摘要: {summary}

## 修改内容
- 修改文件: {', '.join(files[:5])}
- 修改说明: {patch_explanation}
- 风险等级: {risk_level}
- 风险说明: {risk_notes}

## 验证结果
- 整体: {overall}
- pytest: {pytest_result}
- ruff: {ruff_result}
- mypy: {mypy_result}

请以 JSON 格式返回:
{{
    "title": "简洁的 PR 标题（英文，50字以内）",
    "description": "详细的 PR 描述（中文，包括：做了什么、为什么这样做、如何测试）",
    "summary": "一句话总结（中文）",
    "checklist": ["审查项1", "审查项2", "审查项3"]
}}

只返回 JSON。"""

        try:
            response = self.llm.invoke([
                SystemMessage(content="你是专业的代码审查专家，输出精确 JSON。"),
                HumanMessage(content=prompt),
            ])
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text)
        except Exception:
            result = {
                "title": f"Fix: {summary[:50]}",
                "description": f"## 修改说明\n\n{patch_explanation}\n\n## 验证结果\n\n- pytest: {pytest_result}\n- ruff: {ruff_result}\n- mypy: {mypy_result}\n\n## 风险\n\n{risk_notes}",
                "summary": summary,
                "checklist": ["确认修改逻辑正确", "确认测试通过", "检查是否有破坏性变更"],
            }

        result["test_results"] = f"pytest: {pytest_result} | ruff: {ruff_result} | mypy: {mypy_result}"
        result["risk_assessment"] = f"风险等级: {risk_level}. {risk_notes}"
        result["rollback"] = rollback
        return result
