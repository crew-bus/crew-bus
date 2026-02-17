#!/bin/bash
# crew-bus database backup script
# Run via cron: 0 */6 * * * /opt/crew-bus/deploy/backup.sh
# Keeps 14 days of backups

set -euo pipefail

APP_DIR="/opt/crew-bus"
BACKUP_DIR="/opt/crew-bus/backups"
DB_FILE="$APP_DIR/crew_bus.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MAX_AGE_DAYS=14

# Create backup dir
mkdir -p "$BACKUP_DIR"

# SQLite safe backup using .backup command
if [ -f "$DB_FILE" ]; then
    sqlite3 "$DB_FILE" ".backup '$BACKUP_DIR/crew_bus_$TIMESTAMP.db'"

    # Compress
    gzip "$BACKUP_DIR/crew_bus_$TIMESTAMP.db"

    echo "$(date): Backup created: crew_bus_$TIMESTAMP.db.gz"

    # Clean old backups
    find "$BACKUP_DIR" -name "crew_bus_*.db.gz" -mtime "+$MAX_AGE_DAYS" -delete

    echo "$(date): Old backups cleaned (>$MAX_AGE_DAYS days)"
else
    echo "$(date): WARNING — Database file not found: $DB_FILE"
    exit 1
fi
