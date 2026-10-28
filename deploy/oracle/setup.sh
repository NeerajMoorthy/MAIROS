#!/usr/bin/env bash
# Set up the MAIROS API on a fresh Ubuntu VM (Oracle Cloud Always Free).
#
# Run on the VM, from the repository's root, as the default `ubuntu` user:
#
#   bash deploy/oracle/setup.sh
#
# It installs Docker, opens ports 80 and 443 in the VM's own firewall, writes
# deploy/oracle/.env with the public address, asks for the Groq key if the
# repository has no .env yet (typed, never shown), and starts the API behind
# HTTPS. Safe to run again. See docs/ORACLE_VM.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/deploy/oracle"
DATA_PATH="$(dirname "$ROOT")/mairos-data"

echo "== Docker"
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y docker.io docker-compose-v2
fi
sudo systemctl enable --now docker
DOCKER="docker"
if ! docker info >/dev/null 2>&1; then DOCKER="sudo docker"; fi

echo "== Firewall: ports 80 and 443"
# Oracle's Ubuntu images block everything but SSH in iptables, on top of the
# VCN security list (which you open in the console).
for port in 80 443; do
  if ! sudo iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 5 -p tcp --dport "$port" -m state --state NEW -j ACCEPT
  fi
done
if command -v netfilter-persistent >/dev/null 2>&1; then
  sudo netfilter-persistent save
else
  sudo apt-get install -y iptables-persistent
  sudo netfilter-persistent save
fi

echo "== Address"
if [ ! -f "$HERE/.env" ]; then
  ip="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')"
  printf 'DOMAIN=%s.sslip.io\nDATA_PATH=%s\n' "$ip" "$DATA_PATH" > "$HERE/.env"
fi
cat "$HERE/.env"

echo "== Settings (.env)"
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  read -rsp "Groq API key (input hidden; Enter to skip and use the offline model): " key
  echo
  if [ -n "$key" ]; then
    # Replace the example's line without echoing the key anywhere.
    python3 - "$ROOT/.env" "$key" <<'PY'
import re, sys
path, key = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
text, n = re.subn(r"(?m)^GROQ_API_KEY=.*$", lambda _: f"GROQ_API_KEY={key}", text)
if not n:
    text += f"\nGROQ_API_KEY={key}\n"
open(path, "w", encoding="utf-8").write(text)
PY
  fi
  chmod 600 "$ROOT/.env"
fi

echo "== Data folder: $DATA_PATH"
mkdir -p "$DATA_PATH"
# The API container runs as uid 10001 (apps/api/Dockerfile).
sudo chown -R 10001:10001 "$DATA_PATH"

echo "== Build and start (the first build takes 10-20 minutes)"
cd "$HERE"
$DOCKER compose up -d --build

domain="$(grep '^DOMAIN=' "$HERE/.env" | cut -d= -f2)"
echo "== Waiting for https://$domain/api/health"
for _ in $(seq 1 60); do
  if curl -fsS "https://$domain/api/health" >/dev/null 2>&1; then
    echo
    echo "MAIROS API is up at https://$domain"
    echo "Point the website at it (on the PC, in apps/web):"
    echo "  npx vercel env add MAIROS_API_URL production --value https://$domain --force --yes"
    echo "  npx vercel deploy --prod --yes"
    exit 0
  fi
  sleep 10
done
echo "Not answering yet. Check: $DOCKER compose -f $HERE/compose.yaml logs --tail 50" >&2
exit 1
