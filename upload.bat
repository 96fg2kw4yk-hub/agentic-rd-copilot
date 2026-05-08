@echo off
chcp 65001 >nul
echo ========================================
echo   Agentic R^&D Copilot → GitHub上传
echo ========================================
echo.

cd /d C:\Users\liuzhen海\Desktop\项目\agentic-rd-copilot

:: 1. 初始化 Git
if not exist ".git" (
    echo [1/5] 初始化 Git 仓库...
    git init
    echo   已完成
) else (
    echo [1/5] Git 仓库已存在，跳过
)

:: 2. 设置远程
echo [2/5] 设置远程仓库...
git remote remove origin 2>nul
git remote add origin https://github.com/96fg2kw4yk-hub/project.git
echo   远程仓库: https://github.com/96fg2kw4yk-hub/project

:: 3. 暂存
echo [3/5] 暂存文件...
git add .
echo   已完成

:: 4. 提交
echo [4/5] 提交...
git commit -m "feat: Agentic R&D Copilot V3 - AI驱动的多Agent代码修复系统"

:: 5. 推送
echo [5/5] 推送到 GitHub...
git branch -M main
git push -u origin main

if %errorlevel% neq 0 (
    echo.
    echo 推送失败，可能远程已有内容。尝试合并...
    git pull origin main --allow-unrelated-histories
    if %errorlevel% equ 0 (
        git push -u origin main
    ) else (
        echo.
        echo 合并失败。如果远程内容不重要，运行:
        echo   git push -u origin main --force
    )
)

echo.
echo ========================================
echo   完成！https://github.com/96fg2kw4yk-hub/project
echo ========================================
pause
