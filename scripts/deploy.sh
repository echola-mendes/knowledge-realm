#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.docker.example .env
  echo "已创建 .env — 请填写 LLM_API_KEY、SESSION_SECRET、INITIAL_PASSWORD 后重新执行："
  echo "  ./scripts/deploy.sh"
  exit 1
fi

missing=()
for key in LLM_API_KEY SESSION_SECRET INITIAL_PASSWORD; do
  val="$(grep -E "^${key}=" .env | head -1 | cut -d= -f2- || true)"
  if [[ -z "${val// /}" ]]; then
    missing+=("$key")
  fi
done

if ((${#missing[@]})); then
  echo "请在 .env 中填写：${missing[*]}"
  exit 1
fi

docker compose up -d --build

HTTP_PORT="$(grep -E '^HTTP_PORT=' .env | head -1 | cut -d= -f2- || echo 8080)"
HTTP_PORT="${HTTP_PORT:-8080}"

echo ""
echo "部署完成。"
echo "  访问：http://localhost:${HTTP_PORT}"
echo "  健康：http://localhost:${HTTP_PORT}/health"
echo "  日志：docker compose logs -f api worker"
