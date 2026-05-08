"""
测试执行器
==========
职责: 在本地执行 pytest、ruff、mypy 等验证任务。
V3 版本用 subprocess 在本地运行，后续可升级为 Docker 沙箱。
"""

import subprocess
import os
import tempfile
import json


class TestRunner:
    """代码验证执行器"""

    def run_pytest(self, repo_path: str, test_path: str = "") -> dict:
        """运行 pytest"""
        cmd = ["pytest", "-x", "--tb=short"]
        if test_path:
            cmd.append(test_path)
        return self._run_command(cmd, repo_path, "pytest")

    def run_ruff(self, repo_path: str) -> dict:
        """运行 ruff lint 检查"""
        cmd = ["ruff", "check", "--output-format=text"]
        return self._run_command(cmd, repo_path, "ruff")

    def run_mypy(self, repo_path: str) -> dict:
        """运行 mypy 类型检查"""
        cmd = ["mypy", "--ignore-missing-imports", "."]
        return self._run_command(cmd, repo_path, "mypy")

    def run_all(self, repo_path: str) -> dict:
        """运行所有验证"""
        results = {
            "pytest": self.run_pytest(repo_path),
            "ruff": self.run_ruff(repo_path),
            "mypy": self.run_mypy(repo_path),
        }

        all_passed = all(
            r.get("status") == "passed"
            for r in results.values()
        )
        results["overall"] = "passed" if all_passed else "failed"

        return results

    def _run_command(self, cmd: list[str], cwd: str, tool_name: str) -> dict:
        """执行命令并返回结果"""
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {
                "status": "passed" if proc.returncode == 0 else "failed",
                "return_code": proc.returncode,
                "stdout": proc.stdout[:2000],
                "stderr": proc.stderr[:1000],
                "tool": tool_name,
            }
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "tool": tool_name, "error": "执行超时"}
        except FileNotFoundError:
            return {"status": "skipped", "tool": tool_name, "error": f"{tool_name} 未安装"}
        except Exception as e:
            return {"status": "error", "tool": tool_name, "error": str(e)}
