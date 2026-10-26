#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

# Consistent PostgreSQL snapshot plus deployment secrets and application files.
# Redis is a persistent runtime cache, not the authoritative database.
# These local backups contain secrets; keep data/ private and out of Git.
mkdir -p data/backups
exec 9>data/backups/.lock
flock -n 9 || exit 0
backup_dir=$(mktemp -d "data/backups/.pending-XXXXXXXX")
trap 'rm -rf -- "$backup_dir"' EXIT
docker compose exec -T postgres pg_dump -U new_api -d new_api --format=custom > "$backup_dir/database.dump"
test -s "$backup_dir/database.dump"
docker compose exec -T new-api tar -C /data -czf - . > "$backup_dir/application.tar.gz"
cp -- .env docker-compose.production.yml docker-compose.tailnet.yml "$backup_dir/"
tar -czf "$backup_dir/deployment.tar.gz" deployment
if [[ -f data/admin-credentials.txt ]]; then
  cp -- data/admin-credentials.txt "$backup_dir/"
fi
git rev-parse HEAD > "$backup_dir/source-commit.txt"
docker compose images --format json > "$backup_dir/images.json"
chmod 600 "$backup_dir"/*
stamp=$(date -u +%Y%m%dT%H%M%SZ)
destination="data/backups/new-api-$stamp"
mv -T -- "$backup_dir" "$destination"
trap - EXIT
printf 'Backup created: %s\n' "$destination"
# Retain the most recent 14 snapshots, including manual backups. Only delete
# timestamped backup directories, never databases or unrelated directories.
python3 - <<'PY'
from pathlib import Path
import re
import shutil
backups = sorted(p for p in Path('data/backups').iterdir()
                 if p.is_dir() and not p.is_symlink()
                 and re.fullmatch(r'new-api-\d{8}T\d{6}Z', p.name))
for old in backups[:-14]:
    shutil.rmtree(old)
PY
