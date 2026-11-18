#!/usr/bin/env bash
# Health log: every 5 minutes one line about the server (load, memory, swap, processes, Chromium, /tmp, disk,
# kernel pressure). It is a cron job, independent of the bot, so the last lines before a freeze survive it:
#   sudo tail -n 40 /var/log/beeline-health.log
# Install (and update): curl -fsSL <this file's raw URL> | sudo bash
# Remove: sudo rm /etc/cron.d/beeline-health /usr/local/bin/beeline-health
set -Eeuo pipefail

BIN="${HEALTH_BIN:-/usr/local/bin/beeline-health}"
CRON="${HEALTH_CRON:-/etc/cron.d/beeline-health}"
LOG="${HEALTH_LOG:-/var/log/beeline-health.log}"

if [[ $EUID -ne 0 && -z "${HEALTH_NO_ROOT:-}" ]]; then
  echo "ОШИБКА: запусти через sudo" >&2
  exit 1
fi

cat > "$BIN" <<'SH'
#!/bin/sh
LOG="${BEELINE_HEALTH_LOG:-/var/log/beeline-health.log}"
load=$(cut -d' ' -f1-3 /proc/loadavg)
mem=$(free -m | awk '/^Mem:/{printf "mem_used=%d mem_avail=%d", $3, $7}')
swap=$(free -m | awk '/^Swap:/{printf "%d", $3}')
tasks=$(ps -e --no-headers | wc -l)
chrome=$(pgrep -c chrome); [ -n "$chrome" ] || chrome=0
chrome_mb=$(ps -C chrome -o rss= 2>/dev/null | awk '{s+=$1} END{printf "%d", s/1024}')
python_mb=$(ps -C python -o rss= 2>/dev/null | awk '{s+=$1} END{printf "%d", s/1024}')
tmp_mb=$(timeout 20 du -sm /tmp 2>/dev/null | cut -f1); [ -n "$tmp_mb" ] || tmp_mb=-1
disk=$(df --output=pcent / | tail -1 | tr -d ' %')
psi() { awk '/^some/{split($2,a,"="); print a[2]}' "/proc/pressure/$1" 2>/dev/null; }
echo "$(date '+%F %T') load=$load $mem swap_used=$swap tasks=$tasks chrome=$chrome chrome_mb=$chrome_mb python_mb=$python_mb tmp_mb=$tmp_mb disk=${disk}% psi_cpu=$(psi cpu) psi_mem=$(psi memory) psi_io=$(psi io)" >> "$LOG"
if [ "$(wc -l < "$LOG")" -gt 3000 ]; then tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; fi
SH
chmod 0755 "$BIN"

printf '*/5 * * * * root %s >/dev/null 2>&1\n' "$BIN" > "$CRON"
chmod 0644 "$CRON"
BEELINE_HEALTH_LOG="$LOG" "$BIN" || true

echo "Готово: раз в 5 минут строка пишется в $LOG"
echo "Смотреть: sudo tail -n 40 $LOG"
