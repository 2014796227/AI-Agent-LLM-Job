#!/usr/bin/env bash
# 主机 cron: 0 4 * * * /opt/alphadesk/deploy/backup.sh
# 串行链：①pg_dump(MVCC快照,-e注入密码) ②tar数据卷 ③TTL清理
# 数据一致性：工件写入为 tmp→fsync→os.replace 原子操作，
# tar 任意时刻只能拷贝到完整文件——无需暂停写入。
set -euo pipefail
# cron 调用时 cwd=$HOME，而 docker compose 只在 cwd 查找 compose 文件（不像
# git 会向上搜索）——必须先回到脚本所在目录(deploy/)，否则第①步 exec 即报
# "no configuration file provided"（v17 P1-1）
cd "$(dirname "$0")"
STAMP=$(date +%F)
BACKUP_DIR=/var/backups/alphadesk
LOCK=/var/run/alphadesk-backup.lock
API="http://127.0.0.1:8000"
: "${ADMIN_TOKEN:?ADMIN_TOKEN 未设置}"
: "${DB_PASS:?DB_PASS 未设置}"
exec 9>"$LOCK"
flock -n 9 || { echo "backup already running"; exit 1; }
mkdir -p "$BACKUP_DIR/$STAMP"
# ① 先 pg_dump（dump中每行的文件必已在此前原子落盘）
docker compose exec -T -e PGPASSWORD="${DB_PASS}" db \
  pg_dump -U alphadesk alphadesk \
  | gzip > "$BACKUP_DIR/$STAMP/db.sql.gz"
# ② 后 tar 数据卷（appdata=工件+文档统一卷；文件均为原子写的完整文件）
docker run --rm \
  -v alphadesk_appdata:/data \
  -v "$BACKUP_DIR/$STAMP:/out" \
  alpine tar czf /out/appdata.tar.gz -C /data .
# ③ 备份完成后才允许 TTL 清理
curl -s -X POST -H "X-Admin-Token: ${ADMIN_TOKEN}" \
  "$API/api/admin/ttl" || true
echo "backup $STAMP done"
