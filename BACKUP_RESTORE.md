# Бекапи бази даних

Щоденний бекап Postgres налаштований через `scripts/backup_db.sh` + cron на хості VPS
(поза Docker, щоб бекап не залежав від стану самого `web`-контейнера).

## Як це працює

- Cron на хості (root) щодня о 03:00 UTC запускає `scripts/backup_db.sh`.
- Скрипт робить `pg_dump` через `docker compose exec db`, стискає gzip, кладе в
  `/opt/smartshop/backups/smartshop_<timestamp>.sql.gz`.
- Перевіряє цілісність (`gzip -t`) і мінімальний розмір файлу перед тим, як вважати
  бекап успішним.
- Видаляє копії старші за 14 днів (`SMARTSHOP_BACKUP_RETENTION_DAYS`).
- Бекапи зберігаються **локально на тому ж VPS**, що й сама БД - це краще, ніж
  нічого, але не захищає від відмови самого диска/сервера. Якщо зʼявляться
  S3/R2-креденшели, наступний крок - додати вивантаження `OUT_FILE` в
  `scripts/backup_db.sh` (наприклад через `aws s3 cp` або `rclone`).

## Ручний запуск

```bash
cd /opt/smartshop/app
SMARTSHOP_BACKUP_DIR=/opt/smartshop/backups ./scripts/backup_db.sh
```

## Відновлення з бекапу

**Увага:** відновлення перезаписує поточну БД. Спочатку зупиніть `web`, щоб уникнути
запису під час відновлення.

```bash
cd /opt/smartshop/app
docker compose stop web

# Розпакувати потрібний бекап і залити в контейнер db:
gunzip -c /opt/smartshop/backups/smartshop_<timestamp>.sql.gz | \
  docker compose exec -T db psql -U smartshop -d smartshop

docker compose start web
```

Якщо потрібно відновити в ЧИСТУ базу (наприклад, після втрати диска і нового
контейнера `db`), спершу дайте Alembic-міграціям створити порожню схему
(`docker compose up -d db` дочекатися healthy, `docker compose up -d --build web`
один раз, щоб прогнати міграції), а тоді зупиніть `web` і виконайте `psql`-заливку
вище - `pg_dump` без `--clean` очікує порожні таблиці.

## Перевірка, що бекапи справді йдуть

```bash
ls -la /opt/smartshop/backups/
crontab -l   # має містити рядок з backup_db.sh
```
