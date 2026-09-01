#!/usr/bin/env bash
# 실습 준비물(uv, Claude Code)이 없으면 설치한다. 이미 있으면 건너뛴다.
set -euo pipefail

if command -v uv >/dev/null 2>&1; then
    echo "✓ uv 설치됨 ($(uv --version))"
else
    echo "uv 설치 중..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

if command -v claude >/dev/null 2>&1; then
    echo "✓ Claude Code 설치됨 ($(claude --version))"
else
    echo "Claude Code 설치 중..."
    curl -fsSL https://claude.ai/install.sh | bash
fi

echo
echo "준비 완료. 새 터미널을 열거나 shell을 재시작한 뒤 'make run'으로 서버를 띄우세요."
