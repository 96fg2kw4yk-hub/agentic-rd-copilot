"""
评测模块
========
Top-K 定位准确率、MRR、Patch 成功率、测试通过率等指标。
面试时可以直接报数字。
"""

import json
from typing import TypedDict


class EvalMetrics(TypedDict, total=False):
    """评测指标"""
    top1_accuracy: float
    top3_accuracy: float
    top5_accuracy: float
    mrr: float                      # Mean Reciprocal Rank
    patch_success_rate: float
    test_pass_rate: float
    total_cases: int


class Benchmark:
    """Bug 定位与修复评测"""

    def __init__(self):
        self.results = []

    def evaluate_localization(self, predicted_files: list[str],
                               ground_truth_file: str) -> dict:
        """
        评估 Bug 定位效果。

        参数:
        - predicted_files: 模型预测的相关文件列表（按分数降序）
        - ground_truth_file: 真实的 Bug 所在文件

        返回: {top1, top3, top5, reciprocal_rank}
        """
        # 找出 ground_truth 在预测列表中的排名
        rank = None
        for i, f in enumerate(predicted_files):
            if ground_truth_file.endswith(f) or f.endswith(ground_truth_file):
                rank = i + 1
                break

        return {
            "top1": rank == 1,
            "top3": rank is not None and rank <= 3,
            "top5": rank is not None and rank <= 5,
            "reciprocal_rank": 1.0 / rank if rank else 0.0,
            "rank": rank,
        }

    def run_benchmark(self, test_cases: list[dict],
                       workflow_fn) -> dict:
        """
        运行完整评测。

        test_cases: [{"issue_text": "...", "ground_truth_file": "path/to/file.py"}, ...]
        workflow_fn: 调用工作流的函数
        """
        total = len(test_cases)
        top1_count = 0
        top3_count = 0
        top5_count = 0
        mrr_sum = 0.0

        for case in test_cases:
            result = workflow_fn(case["issue_text"], case.get("repo_id", ""))
            predicted_files = [
                f["file_path"]
                for f in result.get("location", {}).get("top_files", [])
            ]
            eval_result = self.evaluate_localization(
                predicted_files, case["ground_truth_file"]
            )

            if eval_result["top1"]: top1_count += 1
            if eval_result["top3"]: top3_count += 1
            if eval_result["top5"]: top5_count += 1
            mrr_sum += eval_result["reciprocal_rank"]

        metrics = EvalMetrics(
            top1_accuracy=round(top1_count / total, 3) if total else 0,
            top3_accuracy=round(top3_count / total, 3) if total else 0,
            top5_accuracy=round(top5_count / total, 3) if total else 0,
            mrr=round(mrr_sum / total, 3) if total else 0,
            total_cases=total,
        )

        self.results.append(metrics)
        return metrics

    def get_summary(self) -> dict:
        """获取评测摘要"""
        return {
            "metrics": self.results[-1] if self.results else {},
            "history": self.results,
        }
