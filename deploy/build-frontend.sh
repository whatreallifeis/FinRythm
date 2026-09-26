#!/usr/bin/env sh
# Собирает фронтенд ruina696 из ветки front в режиме реального API (без моков).
# Код фронтенда не меняется: берётся ровно то, что лежит в origin/front.
# Результат — .deploy/frontend-dist, его раздаёт caddy (deploy/compose.yml).
set -eu
cd "$(dirname "$0")/.."

BRANCH="${FRONT_BRANCH:-front}"
git fetch origin "$BRANCH"
rm -rf .deploy/frontend-src .deploy/frontend-dist
mkdir -p .deploy/frontend-src
git archive "origin/$BRANCH" frontend | tar -x -C .deploy/frontend-src

# VITE_API_URL пустой — фронтенд ходит в /api на том же адресе, что и сам.
docker run --rm \
  -v "$PWD/.deploy/frontend-src/frontend:/app" -w /app \
  -e VITE_USE_MOCK=false -e VITE_API_URL= \
  node:22-alpine sh -c "npm ci --no-audit --no-fund && npm run build"

cp -r .deploy/frontend-src/frontend/dist .deploy/frontend-dist
echo "Фронтенд из origin/$BRANCH ($(git rev-parse --short "origin/$BRANCH")) собран в .deploy/frontend-dist"
