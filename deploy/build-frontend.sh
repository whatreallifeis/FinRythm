#!/usr/bin/env sh
# Собирает фронтенд ruina696 из ветки front (моков в нём нет, все запросы идут в API).
# Код фронтенда не меняется: берётся ровно то, что лежит в origin/front.
# Результат — .deploy/frontend-dist, его раздаёт caddy (deploy/compose.yml).
set -eu
cd "$(dirname "$0")/.."

BRANCH="${FRONT_BRANCH:-front}"
git fetch origin "$BRANCH"
rm -rf .deploy/frontend-src
mkdir -p .deploy/frontend-src .deploy/frontend-dist
git archive "origin/$BRANCH" frontend | tar -x -C .deploy/frontend-src

# VITE_API_URL пустой — фронтенд ходит в /api на том же адресе, что и сам.
docker run --rm \
  -v "$PWD/.deploy/frontend-src/frontend:/app" -w /app \
  -e VITE_API_URL= \
  node:22-alpine sh -c "npm ci --no-audit --no-fund && npm run build"

# Папку не пересоздаём, а меняем её содержимое: caddy смотрит в неё через bind mount,
# и после удаления папки продолжал бы раздавать старую (удалённую) — сайт отвечал 404 до перезапуска caddy.
find .deploy/frontend-dist -mindepth 1 -delete
cp -r .deploy/frontend-src/frontend/dist/. .deploy/frontend-dist/
echo "Фронтенд из origin/$BRANCH ($(git rev-parse --short "origin/$BRANCH")) собран в .deploy/frontend-dist"
