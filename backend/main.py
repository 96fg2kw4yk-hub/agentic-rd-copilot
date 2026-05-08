"""
Agentic R&D Copilot — FastAPI 服务
====================================
API 接口:
- POST /api/repos/import     → 导入 GitHub 仓库
- POST /api/repos/{id}/index → 建立代码索引
- POST /api/issues/analyze   → 分析 Issue + 定位 Bug
- GET  /api/tasks/{id}       → 获取分析结果
- GET  /                     → 前端页面
"""

import os
import json
import uuid
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *
from indexer.repo_indexer import RepoIndexer
from workflow import run_analysis, run_full_pipeline
from eval.benchmark import Benchmark


# ============ 初始化 ============
app = FastAPI(
    title="Agentic R&D Copilot V3",
    description="企业级 Agentic R&D Copilot — Issue→定位→Patch→验证→PR 全链路",
    version="3.0.0",
)

benchmark = Benchmark()

indexer = RepoIndexer()

# 任务存储（V1 用内存字典，后续可换数据库）
tasks: dict[str, dict] = {}
repo_map: dict[str, str] = {}  # repo_id → local_path


# ============ 请求/响应模型 ============
class ImportRepoRequest(BaseModel):
    repo_url: str
    branch: str = "main"

class ImportLocalRequest(BaseModel):
    local_path: str

class IssueAnalysisRequest(BaseModel):
    repo_id: str
    issue_text: str


# ============ API ============

@app.post("/api/repos/import-local")
async def import_local(req: ImportLocalRequest):
    """导入本地文件夹"""
    result = indexer.import_local(req.local_path)
    if result["status"] != "error":
        repo_map[result["repo_id"]] = result["local_path"]
    return JSONResponse(result)

@app.post("/api/repos/import")
async def import_repo(req: ImportRepoRequest):
    """导入 GitHub 仓库"""
    result = indexer.import_repo(req.repo_url, req.branch)
    if result["status"] not in ("error",):
        repo_map[result["repo_id"]] = result["local_path"]
    return JSONResponse(result)


@app.post("/api/repos/{repo_id}/index")
async def index_repo(repo_id: str):
    """为仓库建立代码索引（AST 解析 + 向量 + BM25）"""
    # 先从 repo_map 查找
    repo_path = repo_map.get(repo_id)

    # 再从磁盘查找
    if not repo_path:
        for dirname in os.listdir(REPOS_DIR):
            full_path = os.path.join(REPOS_DIR, dirname)
            if os.path.isdir(full_path) and repo_id in dirname:
                repo_path = full_path
                break

    if not repo_path or not os.path.isdir(repo_path):
        raise HTTPException(status_code=404, detail="仓库未找到，请先导入")

    # 扫描解析
    stats = indexer.scan_and_parse(repo_id, repo_path)
    # 建立向量索引
    vec_result = indexer.build_vector_index()
    # 建立 BM25 索引
    indexer.build_bm25_index()

    return JSONResponse({
        "repo_id": repo_id,
        "status": "indexed",
        "stats": indexer.get_stats(),
        "vector_index": vec_result,
    })


@app.post("/api/issues/analyze")
async def analyze_issue(req: IssueAnalysisRequest):
    """分析 Issue 并定位 Bug"""
    # 检查索引是否就绪
    if not indexer.chunks:
        raise HTTPException(status_code=400, detail="请先为仓库建立索引")

    if indexer.current_repo_id != req.repo_id:
        raise HTTPException(status_code=400, detail="仓库 ID 不匹配，请检查")

    # 创建任务
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    tasks[task_id] = {
        "task_id": task_id,
        "repo_id": req.repo_id,
        "issue_text": req.issue_text,
        "status": "running",
        "created_at": datetime.now().isoformat(),
        "result": None,
    }

    # 执行分析
    try:
        result = run_analysis(req.issue_text, req.repo_id)
        tasks[task_id]["status"] = "done"
        tasks[task_id]["result"] = {
            "issue_analysis": result.get("issue_analysis", {}),
            "location": result.get("location", {}),
        }
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["result"] = {"error": str(e)}

    return JSONResponse({
        "task_id": task_id,
        "status": tasks[task_id]["status"],
    })


@app.post("/api/issues/analyze-full")
async def analyze_full_pipeline(req: IssueAnalysisRequest):
    """V3 全链路：Issue→定位→Patch→验证→PR"""
    if not indexer.chunks:
        raise HTTPException(status_code=400, detail="请先为仓库建立索引")
    if indexer.current_repo_id != req.repo_id:
        raise HTTPException(status_code=400, detail="仓库 ID 不匹配")

    task_id = f"task_{uuid.uuid4().hex[:8]}"
    tasks[task_id] = {
        "task_id": task_id, "repo_id": req.repo_id,
        "issue_text": req.issue_text, "status": "running",
        "created_at": datetime.now().isoformat(), "result": None,
    }

    try:
        repo_path = repo_map.get(req.repo_id, "")
        result = run_full_pipeline(req.issue_text, req.repo_id, repo_path)
        tasks[task_id]["status"] = "done"
        tasks[task_id]["result"] = {
            "issue_analysis": result.get("issue_analysis", {}),
            "location": result.get("location", {}),
            "patch": result.get("patch", {}),
            "verification": result.get("verification", {}),
            "pr": result.get("pr", {}),
        }
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["result"] = {"error": str(e)}

    return JSONResponse({"task_id": task_id, "status": tasks[task_id]["status"]})


@app.post("/api/eval/run")
async def run_eval(req: IssueAnalysisRequest):
    """运行 Benchmark 评测"""
    result = run_analysis(req.issue_text, req.repo_id)
    predicted = [f["file_path"] for f in result.get("location", {}).get("top_files", [])]

    # 需要 ground_truth，从请求中获取或使用默认
    gt_file = req.issue_text.split("\n")[0].strip() if "\n" in req.issue_text else ""
    metrics = benchmark.evaluate_localization(predicted, gt_file)

    return JSONResponse({
        "predicted_files": predicted,
        "metrics": metrics,
        "summary": benchmark.get_summary(),
    })


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    """获取任务结果"""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return JSONResponse(task)


@app.get("/api/repos/{repo_id}/stats")
async def get_stats(repo_id: str):
    """获取仓库索引统计"""
    return JSONResponse(indexer.get_stats())


@app.get("/api/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "indexed": len(indexer.chunks) > 0,
        "repo_id": indexer.current_repo_id,
        "tasks": len(tasks),
    }


@app.get("/", response_class=HTMLResponse)
async def homepage():
    """前端页面"""
    html_path = os.path.join(BASE_DIR, "frontend", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>前端页面未找到</h1>"


# ============ 启动 ============
if __name__ == "__main__":
    print("=" * 50)
    print("  Agentic R&D Copilot v1.0")
    print("  访问: http://localhost:8090")
    print("=" * 50)
    uvicorn.run(app, host=HOST, port=PORT)
