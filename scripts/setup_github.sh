#!/usr/bin/env bash
# Запускает Вероника один раз после создания репозитория. Нужен gh (GitHub CLI), выполнен gh auth login.
set -euo pipefail
for l in "to:veronika:1D76DB" "to:sasha:0E8A16" "to:sonya:B60205" "to:kirill:5319E7" \
         "contract:D93F0B" "blocked:000000" "bug:D73A4A" "S-priority:C5DEF5"; do
  name="${l%:*}"; color="${l##*:}"
  gh label create "$name" --color "$color" --force
done
echo "Метки созданы."
