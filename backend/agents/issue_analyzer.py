"""
Issue 分析 Agent
================
职责: 将自然语言 Issue / 错误日志 / 测试失败信息结构化。
输出: 问题类型、关键词、错误堆栈、可能涉及的模块、严重程度。
"""

import json
import re
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import LLM_MODEL


class IssueAnalyzer:
    """Issue 分析 Agent"""

    def __init__(self):
        self.llm = ChatOllama(model=LLM_MODEL, temperature=0.1)

    def analyze(self, issue_text: str, repo_name: str = "") -> dict:
        """
        分析 Issue 文本，提取结构化信息。

        输入示例:
            "用户登录后偶发 500，日志显示 JWT decode failed"

        输出:
            {
                "issue_type": "runtime_error",
                "keywords": ["JWT", "decode", "login", "500"],
                "error_stack": "JWT decode failed",
                "possible_modules": ["auth", "middleware", "token"],
                "severity": "medium",
                "summary": "JWT token 解码异常导致登录 500 错误"
            }
        """
        # 先用正则提取明显的错误信息
        error_stack = self._extract_error_stack(issue_text)

        # 让 LLM 做结构化分析
        prompt = f"""你是一个资深软件工程师，请分析以下 Issue 或错误报告，提取关键信息。

Issue 内容:
{issue_text}

{'提取到的错误堆栈: ' + error_stack if error_stack else ''}

请以 JSON 格式返回分析结果:
{{
    "issue_type": "bug|runtime_error|test_failure|performance|security|feature_request",
    "keywords": ["关键词1", "关键词2", ...],  // 5-10个技术相关的关键词
    "possible_modules": ["模块1", "模块2"],  // 可能涉及的功能模块
    "severity": "critical|high|medium|low",
    "summary": "用一句话概括问题",
    "error_type": "具体的错误类型，如 AttributeError, ImportError 等",
    "reproduction_hint": "复现条件或触发场景的描述"
}}

只返回 JSON，不要其他文字。"""

        try:
            response = self.llm.invoke([
                SystemMessage(content="你是专业的软件 Issue 分析专家，输出精确的 JSON。"),
                HumanMessage(content=prompt),
            ])
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text)
        except Exception:
            # LLM 调用失败，用正则做退化分析
            result = self._fallback_analyze(issue_text)

        # 补充错误堆栈
        result["error_stack"] = error_stack
        result["original_issue"] = issue_text[:500]
        result["repo_name"] = repo_name

        return result

    def _extract_error_stack(self, text: str) -> str:
        """从 Issue 文本中提取错误堆栈"""
        # 匹配常见错误堆栈格式
        patterns = [
            r'(Traceback\s*\(most recent call last\):.*?)(?:\n\n|\Z)',  # Python traceback
            r'(Error:.*?)(?:\n\n|\Z)',  # Error: ...
            r'(Exception:.*?)(?:\n\n|\Z)',  # Exception: ...
            r'(\w+Error:.*?)(?:\n|$)',  # XxxError: ...
            r'(\w+Exception:.*?)(?:\n|$)',  # XxxException: ...
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()[:500]
        return ""

    def _fallback_analyze(self, text: str) -> dict:
        """当 LLM 不可用时的退化分析"""
        # 提取关键词
        keywords = []
        # 错误类型匹配
        error_types = [
            "AttributeError", "TypeError", "ValueError", "KeyError", "IndexError",
            "ImportError", "ModuleNotFoundError", "NameError", "SyntaxError",
            "ConnectionError", "TimeoutError", "FileNotFoundError", "PermissionError",
            "AssertionError", "RuntimeError", "OSError", "IOError",
        ]
        for et in error_types:
            if et.lower() in text.lower() or et.replace("Error", "").lower() in text.lower():
                keywords.append(et)

        # HTTP 状态码
        http_codes = re.findall(r'\b(4\d{2}|5\d{2})\b', text)
        for code in http_codes:
            keywords.append(f"HTTP {code}")

        # 常见技术词
        tech_words = ["JWT", "token", "auth", "login", "database", "SQL", "API",
                       "request", "response", "timeout", "null", "None", "undefined",
                       "decode", "encode", "parse", "serialize", "deserialize"]
        for word in tech_words:
            if word.lower() in text.lower():
                keywords.append(word)

        # 判断严重程度
        severity = "medium"
        if any(w in text.lower() for w in ["critical", "崩溃", "crash", "500", "502", "503"]):
            severity = "critical"
        elif any(w in text.lower() for w in ["error", "错误", "失败", "failed"]):
            severity = "high"

        return {
            "issue_type": "bug",
            "keywords": list(set(keywords))[:10],
            "possible_modules": [],
            "severity": severity,
            "summary": text[:100],
            "error_type": keywords[0] if keywords else "unknown",
            "reproduction_hint": "",
        }
