# ═══════════════════════════════════════
# Agentic R&D Copilot → GitHub 上传脚本
# 目标仓库: https://github.com/96fg2kw4yk-hub/project
# ═══════════════════════════════════════

$ErrorActionPreference = "Stop"
$repoPath = "C:\Users\liuzhen海\Desktop\项目\agentic-rd-copilot"
$remoteUrl = "https://github.com/96fg2kw4yk-hub/project.git"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Agentic R&D Copilot → GitHub 上传" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $repoPath

# 1. 初始化 Git（如果还没有）
if (-not (Test-Path ".git")) {
    Write-Host "[1/5] 初始化 Git 仓库..." -ForegroundColor Yellow
    git init
    Write-Host "  ✓ Git 仓库已初始化" -ForegroundColor Green
} else {
    Write-Host "[1/5] Git 仓库已存在，跳过初始化" -ForegroundColor Yellow
}

# 2. 设置远程仓库
Write-Host "[2/5] 设置远程仓库..." -ForegroundColor Yellow
$existingRemote = git remote get-url origin 2>$null
if ($existingRemote) {
    git remote set-url origin $remoteUrl
    Write-Host "  ✓ 远程仓库已更新: $remoteUrl" -ForegroundColor Green
} else {
    git remote add origin $remoteUrl
    Write-Host "  ✓ 远程仓库已添加: $remoteUrl" -ForegroundColor Green
}

# 3. 暂存所有文件
Write-Host "[3/5] 暂存文件（已排除 .venv, data/repos, __pycache__ 等）..." -ForegroundColor Yellow
git add .
Write-Host "  ✓ 文件已暂存" -ForegroundColor Green

# 显示将要提交的文件
Write-Host ""
Write-Host "  将要提交的文件:" -ForegroundColor Gray
git status --short

# 4. 提交
Write-Host ""
Write-Host "[4/5] 提交..." -ForegroundColor Yellow
$commitMsg = "feat: Agentic R&D Copilot V3 - AI驱动的多Agent代码修复系统"
git commit -m $commitMsg
Write-Host "  ✓ 提交完成" -ForegroundColor Green

# 5. 推送
Write-Host "[5/5] 推送到 GitHub..." -ForegroundColor Yellow
git branch -M main

# 尝试正常推送
$pushResult = git push -u origin main 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  正常推送失败，可能是因为远程仓库已有内容。" -ForegroundColor Yellow
    Write-Host "  尝试合并远程内容后推送..." -ForegroundColor Yellow
    git pull origin main --allow-unrelated-histories --no-edit
    if ($LASTEXITCODE -eq 0) {
        git push -u origin main
    } else {
        Write-Host ""
        Write-Host "  ⚠ 自动合并失败。" -ForegroundColor Red
        Write-Host "  如果远程仓库内容不重要，可以强制推送：" -ForegroundColor Yellow
        Write-Host "  git push -u origin main --force" -ForegroundColor Red
        Write-Host "  ⚠ 警告: 强制推送会覆盖远程仓库的所有内容！" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  ✓ 上传完成！" -ForegroundColor Green
Write-Host "  查看: https://github.com/96fg2kw4yk-hub/project" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
