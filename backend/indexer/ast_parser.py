"""
AST 代码解析器
==============
用 Python 内置 ast 模块解析 .py 文件，提取:
- 文件级摘要
- 函数（名称、参数、返回值、docstring、行号）
- 类（名称、方法、继承关系）
- import 关系
- 测试函数

输出结构化 chunk，供后续向量化和 BM25 索引使用。
"""

import ast
import os
from dataclasses import dataclass, field, asdict


@dataclass
class CodeChunk:
    """代码片段的结构化表示"""
    chunk_id: str
    repo_id: str
    file_path: str
    symbol_type: str          # "file" | "class" | "function" | "method" | "test"
    symbol_name: str
    start_line: int
    end_line: int
    content: str              # 原始代码
    summary: str = ""         # LLM 生成的摘要（可选）
    docstring: str = ""
    imports: list[str] = field(default_factory=list)
    parent_class: str = ""    # 如果是方法，记录所属类
    decorators: list[str] = field(default_factory=list)
    params: list[str] = field(default_factory=list)
    returns: str = ""


class ASTParser:
    """Python 代码 AST 解析器"""

    def parse_file(self, repo_id: str, file_path: str, source_code: str) -> list[CodeChunk]:
        """
        解析一个 Python 文件，返回结构化 chunk 列表。
        包含: 文件级 chunk + 类级 chunk + 函数/方法级 chunk
        """
        chunks = []
        rel_path = self._get_rel_path(file_path)

        # 1. 文件级 chunk（整体概览）
        file_chunk = CodeChunk(
            chunk_id=f"{repo_id}:{rel_path}:file",
            repo_id=repo_id,
            file_path=rel_path,
            symbol_type="file",
            symbol_name=rel_path,
            start_line=1,
            end_line=len(source_code.split("\n")),
            content=source_code[:2000],  # 文件级只存前 2000 字符
        )
        chunks.append(file_chunk)

        # 2. 解析 AST
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return chunks  # 语法错误的文件只保留文件级 chunk

        # 3. 提取所有 import
        all_imports = self._extract_imports(tree)

        # 4. 遍历顶层节点
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef):
                chunk = self._parse_function(node, repo_id, rel_path, source_code, all_imports, is_method=False)
                chunks.append(chunk)

            elif isinstance(node, ast.ClassDef):
                # 类级 chunk
                class_chunk = self._parse_class(node, repo_id, rel_path, source_code, all_imports)
                chunks.append(class_chunk)

                # 类的方法
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        method_chunk = self._parse_function(
                            item, repo_id, rel_path, source_code, all_imports,
                            is_method=True, parent_class=node.name
                        )
                        chunks.append(method_chunk)

        return chunks

    def _parse_function(self, node: ast.FunctionDef, repo_id: str, file_path: str,
                        source_code: str, imports: list[str], is_method: bool = False,
                        parent_class: str = "") -> CodeChunk:
        """解析单个函数/方法"""
        func_name = node.name
        symbol_type = "test" if func_name.startswith("test_") else ("method" if is_method else "function")

        # 提取参数
        params = []
        for arg in node.args.args:
            params.append(arg.arg)

        # 提取 docstring
        docstring = ast.get_docstring(node) or ""

        # 提取装饰器
        decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Attribute):
                decorators.append(self._get_attr_name(dec))

        # 提取函数体代码
        lines = source_code.split("\n")
        start = node.lineno
        end = node.end_lineno or start
        content = "\n".join(lines[start-1:end])

        # 生成摘要
        summary = self._make_summary(symbol_type, func_name, params, docstring)

        chunk = CodeChunk(
            chunk_id=f"{repo_id}:{file_path}:{func_name}",
            repo_id=repo_id,
            file_path=file_path,
            symbol_type=symbol_type,
            symbol_name=func_name,
            start_line=start,
            end_line=end,
            content=content,
            summary=summary,
            docstring=docstring,
            imports=imports,
            parent_class=parent_class,
            decorators=decorators,
            params=params,
        )
        return chunk

    def _parse_class(self, node: ast.ClassDef, repo_id: str, file_path: str,
                     source_code: str, imports: list[str]) -> CodeChunk:
        """解析类定义"""
        # 提取继承关系
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)

        # 提取类体代码
        lines = source_code.split("\n")
        start = node.lineno
        end = node.end_lineno or start
        content = "\n".join(lines[start-1:end])

        docstring = ast.get_docstring(node) or ""
        summary = f"类 {node.name}" + (f" 继承自 {', '.join(bases)}" if bases else "")

        # 列出所有方法
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods.append(item.name)

        chunk = CodeChunk(
            chunk_id=f"{repo_id}:{file_path}:{node.name}",
            repo_id=repo_id,
            file_path=file_path,
            symbol_type="class",
            symbol_name=node.name,
            start_line=start,
            end_line=end,
            content=content,
            summary=summary,
            docstring=docstring,
            imports=imports,
        )
        return chunk

    def _extract_imports(self, tree: ast.AST) -> list[str]:
        """提取文件中所有的 import 语句"""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}" if module else alias.name)
        return imports

    def _make_summary(self, symbol_type: str, name: str, params: list[str], docstring: str) -> str:
        """生成代码片段摘要"""
        type_label = {
            "function": "函数",
            "method": "方法",
            "test": "测试",
        }.get(symbol_type, "符号")

        summary = f"{type_label} {name}"
        if params:
            summary += f"({', '.join(params)})"
        if docstring:
            summary += f": {docstring[:100]}"
        return summary

    def _get_rel_path(self, file_path: str) -> str:
        """获取相对于仓库根目录的路径"""
        # 简单处理：取 repos/ 之后的部分
        parts = file_path.replace("\\", "/").split("/")
        if "repos" in parts:
            idx = parts.index("repos")
            # 跳过 repos/{repo_name}/
            return "/".join(parts[idx+2:])
        return file_path

    def _get_attr_name(self, node: ast.Attribute) -> str:
        """递归获取 ast.Attribute 的完整名称"""
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
