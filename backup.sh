#!/bin/sh
# SQLite-Backup fuer bierkaessle
# Cron-Beispiel (taeglich 03:00 Uhr):
#   0 3 * * * /pfad/zu/backup.sh >> /var/log/bierkaessle_backup.log 2>&1

DB_PATH="${DB_PATH:-/app/instance/bierkaessle.sqlite3}"
BACKUP_DIR="${BACKUP_DIR:-/backups/bierkaessle}"
DATE=$(date +"%Y-%m-%d_%H-%M")
BACKUP_FILE="${BACKUP_DIR}/bierkaessle_${DATE}.sql"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_PATH" ]; then
  echo "[$(date)] FEHLER: Datenbank nicht gefunden: $DB_PATH"
  exit 1
fi

sqlite3 "$DB_PATH" .dump > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
  echo "[$(date)] Backup erstellt: $BACKUP_FILE"
else
  echo "[$(date)] FEHLER beim Erstellen des Backups!"
  exit 1
fi

find "$BACKUP_DIR" -name "bierkaessle_*.sql" -mtime +"$KEEP_DAYS" -delete
echo "[$(date)] Backups aelter als ${KEEP_DAYS} Tage geloescht."
