#!/usr/bin/env bash
# Щоденний бекап Postgres для SmartShop AI.
# Дампить БД з контейнера db, стискає, кладе в BACKUP_DIR, ротує старі копії.
# Розрахований на запуск з хоста (не з контейнера) через cron, з робочої
# директорії репозиторію (там, де лежить docker-compose.yml).
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${SMARTSHOP_BACKUP_DIR:-/opt/smartshop/backups}"
RETENTION_DAYS="${SMARTSHOP_BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
OUT_FILE="${BACKUP_DIR}/smartshop_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"
cd "${APP_DIR}"

POSTGRES_USER="$(grep -E '^POSTGRES_USER=' .env.docker 2>/dev/null | cut -d= -f2- || true)"
POSTGRES_DB="$(grep -E '^POSTGRES_DB=' .env.docker 2>/dev/null | cut -d= -f2- || true)"
POSTGRES_USER="${POSTGRES_USER:-smartshop}"
POSTGRES_DB="${POSTGRES_DB:-smartshop}"

docker compose exec -T db pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" | gzip > "${OUT_FILE}.part"
mv "${OUT_FILE}.part" "${OUT_FILE}"

# Перевірка, що дамп не порожній/не биті (gzip -t валідує стиснутий потік)
gzip -t "${OUT_FILE}"
SIZE_BYTES=$(stat -c%s "${OUT_FILE}" 2>/dev/null || stat -f%z "${OUT_FILE}")
if [ "${SIZE_BYTES}" -lt 1024 ]; then
    echo "WARNING: backup file suspiciously small (${SIZE_BYTES} bytes): ${OUT_FILE}" >&2
    exit 1
fi

find "${BACKUP_DIR}" -name 'smartshop_*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete

echo "OK: ${OUT_FILE} (${SIZE_BYTES} bytes)"
