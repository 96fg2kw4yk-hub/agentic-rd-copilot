"""
Agentic R&D Copilot — LangGraph 全链路工作流 (V3)
===================================================
6 Agent 串联:
    Issue 分析 → 代码检索 → Bug 定位 → Patch 生成 → 验证 → PR 生成

使用方式:
    基础（V1）: run_analysis(issue_text, repo_id)
    完整（V3）: run_full_pipeline(issue_text, repo_id, repo_path)
"""

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.issue_analyzer import IssueAnalyzer
from agents.bug_locator import BugLocator
from agents.patch_generator import PatchGenerator
from agents.pr_agent import PRAgent
from tools.test_runner import TestRunner
from indexer.repo_indexer import RepoIndexer


# ============ 状态定义 ============
class PipelineState(TypedDict):
    issue_text: str
    repo_id: str
    repo_path: str
    # 各阶段输出
    issue_analysis: dict
    search_results: list
    location: dict
    patch: dict
    verification: dict
    pr: dict
    # 状态
    status: str
    error: str
    mode: str            # "basic" | "full"


# ============ 初始化 ============
issue_analyzer = IssueAnalyzer()
bug_locator = BugLocator()
patch_generator = PatchGenerator()
pr_agent = PRAgent()
test_runner = TestRunner()
indexer = RepoIndexer()


# ============ 节点函数 ============

def analyze_issue_node(state: PipelineState) -> PipelineState:
    print(f"[Workflow] ① Issue 分析: {state['issue_text'][:60]}...")
    state["issue_analysis"] = issue_analyzer.analyze(state["issue_text"])
    state["status"] = "issue_analyzed"
    return state


def search_code_node(state: PipelineState) -> PipelineState:
    analysis = state.get("issue_analysis", {})
    keywords = " ".join(analysis.get("keywords", []))
    summary = analysis.get("summary", "")
    query = f"{summary} {keywords}" if summary else keywords
    print(f"[Workflow] ② 代码检索: {query[:60]}...")
    state["search_results"] = indexer.hybrid_search(query, repo_id=state["repo_id"])
    state["status"] = "code_searched"
    return state


def locate_bug_node(state: PipelineState) -> PipelineState:
    print("[Workflow] ③ Bug 定位...")
    state["location"] = bug_locator.locate(
        state["issue_analysis"], state["search_results"]
    )
    state["status"] = "bug_located"
    return state


def generate_patch_node(state: PipelineState) -> PipelineState:
    print("[Workflow] ④ Patch 生成...")
    state["patch"] = patch_generator.generate(
        state["issue_analysis"], state["location"]
    )
    state["status"] = "patch_generated"
    return state


def verify_node(state: PipelineState) -> PipelineState:
    print("[Workflow] ⑤ 测试验证...")
    repo_path = state.get("repo_path", "")
    if repo_path and os.path.isdir(repo_path):
        state["verification"] = test_runner.run_all(repo_path)
    else:
        state["verification"] = {
            "overall": "skipped",
            "pytest": {"status": "skipped", "error": "仓库路径未提供"},
            "ruff": {"status": "skipped"},
            "mypy": {"status": "skipped"},
        }
    state["status"] = "verified"
    return state


def generate_pr_node(state: PipelineState) -> PipelineState:
    print("[Workflow] ⑥ PR 生成...")
    state["pr"] = pr_agent.generate(
        state["issue_analysis"],
        state["location"],
        state["patch"],
        state["verification"],
    )
    state["status"] = "done"
    return state


def decide_mode(state: PipelineState) -> str:
    """根据 mode 决定走基础路径还是完整路径"""
    mode = state.get("mode", "full")
    if mode == "basic":
        return "done_basic"
    return "generate_patch"


def decide_after_verify(state: PipelineState) -> str:
    """验证通过后生成 PR"""
    return "generate_pr"


# ============ 构建图 ============

def build_workflow(mode: str = "basic"):
    """
    构建状态图。
    mode="basic"  → Issue分析→检索→定位 (V1)
    mode="full"   → 全部6步 (V3)
    """
    workflow = StateGraph(PipelineState)

    # 核心节点
    workflow.add_node("analyze_issue", analyze_issue_node)
    workflow.add_node("search_code", search_code_node)
    workflow.add_node("locate_bug", locate_bug_node)

    workflow.set_entry_point("analyze_issue")
    workflow.add_edge("analyze_issue", "search_code")
    workflow.add_edge("search_code", "locate_bug")

    if mode == "full":
        workflow.add_node("generate_patch", generate_patch_node)
        workflow.add_node("verify", verify_node)
        workflow.add_node("generate_pr", generate_pr_node)

        workflow.add_conditional_edges(
            "locate_bug", decide_mode,
            {"generate_patch": "generate_patch", "done_basic": END}
        )
        workflow.add_edge("generate_patch", "verify")
        workflow.add_edge("verify", "generate_pr")
        workflow.add_edge("generate_pr", END)
    else:
        workflow.add_edge("locate_bug", END)

    return workflow.compile()


# ============ 执行入口 ============

def run_analysis(issue_text: str, repo_id: str) -> dict:
    """V1: Issue 分析 + 检索 + Bug 定位"""
    graph = build_workflow(mode="basic")
    state = {
        "issue_text": issue_text, "repo_id": repo_id, "repo_path": "",
        "issue_analysis": {}, "search_results": [], "location": {},
        "patch": {}, "verification": {}, "pr": {},
        "status": "starting", "error": "", "mode": "basic",
    }
    return graph.invoke(state)


def run_full_pipeline(issue_text: str, repo_id: str, repo_path: str = "") -> dict:
    """V3: 完整的 6 Agent 全链路"""
    graph = build_workflow(mode="full")
    state = {
        "issue_text": issue_text, "repo_id": repo_id, "repo_path": repo_path,
        "issue_analysis": {}, "search_results": [], "location": {},
        "patch": {}, "verification": {}, "pr": {},
        "status": "starting", "error": "", "mode": "full",
    }
    return graph.invoke(state)
