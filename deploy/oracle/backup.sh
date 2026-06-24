#!/bin/bash
# SQLite 자동 백업 스크립트
# 매일 실행 — 7일치 보관, 매주 일요일 주간 백업 별도 보관

DB_FILE="/home/ubuntu/app/data/sales_intelligence.db"
BACKUP_DIR="/home/ubuntu/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DOW=$(date +%u)  # 1=월 ~ 7=일

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

# 일별 백업
cp "$DB_FILE" "$BACKUP_DIR/daily/db_${DATE}.db"
echo "[$(date)] Daily backup: db_${DATE}.db"

# 7일 넘은 일별 백업 삭제
find "$BACKUP_DIR/daily" -name "*.db" -mtime +7 -delete

# 일요일이면 주간 백업 추가 (4주 보관)
if [ "$DOW" -eq 7 ]; then
    cp "$DB_FILE" "$BACKUP_DIR/weekly/db_weekly_${DATE}.db"
    echo "[$(date)] Weekly backup: db_weekly_${DATE}.db"
    find "$BACKUP_DIR/weekly" -name "*.db" -mtime +28 -delete
fi

# 백업 목록 출력
echo "[$(date)] Backup status:"
ls -lh "$BACKUP_DIR/daily/" | tail -5
