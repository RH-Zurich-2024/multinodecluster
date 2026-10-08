#!/usr/bin/env bash
# ==============================================================================
# inject-iptables.sh
# Störungs-Simulator für die Seminararbeit (Transiente Netzwerkfehler via Kernel)
#
# Simuliert Paketverlust oder Latenz zur Git-Quelle (GitHub Port 443),
# um transiente Zwischenzustände (Degraded) und Exponential Backoff zu provozieren.
# ==============================================================================

set -euo pipefail

# Standard-Parameter
PROBABILITY="${PROBABILITY:-0.40}"  # 40% Paketverlust als Standard-Teilausfall
DURATION="${DURATION:-120}"         # Störungsdauer in Sekunden (Standard: 2 Minuten)
TARGET_PORT="${TARGET_PORT:-443}"   # Zielport (HTTPS / Git-Sync)
TARGET_DOMAIN="github.com"

# Hilfsfunktionen
log_info()  { echo -e "\033[1;34m[INFO]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $*"; }
log_warn()  { echo -e "\033[1;33m[WARN]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $*"; }
log_chaos() { echo -e "\033[1;31m[CHAOS]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $*"; }
log_ok()    { echo -e "\033[1;32m[OK]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $*"; }

cleanup() {
  log_info "Bereinige Firewall- und Traffic-Control-Regeln..."
  # Entferne gezielt unsere iptables-Drop-Regeln
  while iptables -D OUTPUT -p tcp --dport "$TARGET_PORT" -m statistic --mode random --probability "$PROBABILITY" -j DROP 2>/dev/null; do
    log_info "iptables-Drop-Regel entfernt."
  done
  # Sicherheits-Flush für eventuelle Restregeln mit Kommentar
  iptables -S OUTPUT | grep "gitops-chaos" | sed 's/-A/-D/' | while read -r rule; do
    eval "iptables $rule" 2>/dev/null || true
  done
  log_ok "Netzwerk vollständig normalisiert. Keine aktiven Störungen mehr."
}

# Trap sorgt dafür, dass bei Skriptabbruch (Ctrl+C, SIGTERM) das Netzwerk wieder sauber ist
trap cleanup EXIT INT TERM

show_status() {
  echo "=== Aktive iptables OUTPUT-Regeln ==="
  iptables -L OUTPUT -v -n --line-numbers
  echo ""
  echo "=== TCP Retransmission Statistik (Kernel) ==="
  netstat -s | grep -i retrans || true
}

inject_packet_loss() {
  log_chaos "Starte transiente Störung: ${PROBABILITY} Paketverlust auf Port ${TARGET_PORT} (${TARGET_DOMAIN})"
  log_info "Dauer der Störung: ${DURATION} Sekunden"

  # Regel im Kernel aktivieren mit Kommentar zur sauberen Identifikation
  iptables -A OUTPUT -p tcp --dport "$TARGET_PORT" \
    -m statistic --mode random --probability "$PROBABILITY" \
    -m comment --comment "gitops-chaos" \
    -j DROP

  log_ok "Kernel-Regel aktiv! Beobachte jetzt den Status in ArgoCD (Erwartung: 'Progressing' -> 'Degraded')."

  # Countdown mit Live-Paketverlust-Zähler
  local remaining=$DURATION
  while [ $remaining -gt 0 ]; do
    local dropped_packets
    dropped_packets=$(iptables -L OUTPUT -v -n | grep "gitops-chaos" | awk '{print $1}' || echo "0")
    echo -ne "\r\033[1;31m[CHAOS AKTIV]\033[0m Restzeit: ${remaining}s | Bisher verworfene Pakete: ${dropped_packets}  "
    sleep 5
    remaining=$((remaining - 5))
  done
  echo ""

  log_info "Störungszeitfenster abgelaufen. Beginne Erholungsphase..."
}

# CLI-Verarbeitung
case "${1:-inject}" in
  inject)
    inject_packet_loss
    ;;
  cleanup)
    cleanup
    trap - EXIT INT TERM
    exit 0
    ;;
  status)
    show_status
    trap - EXIT INT TERM
    exit 0
    ;;
  help|--help|-h)
    echo "Verwendung: $0 [inject|cleanup|status]"
    echo ""
    echo "Umgebungsvariablen:"
    echo "  PROBABILITY   Wahrscheinlichkeit des Paketverlusts (Standard: 0.40 = 40%)"
    echo "  DURATION      Dauer der Störung in Sekunden (Standard: 120)"
    echo "  TARGET_PORT   Zielport für Paketverlust (Standard: 443 für HTTPS/Git)"
    echo ""
    echo "Beispiel:"
    echo "  PROBABILITY=0.50 DURATION=60 sudo ./inject-iptables.sh inject"
    trap - EXIT INT TERM
    exit 0
    ;;
  *)
    echo "Unbekannter Befehl: $1 (Verwende: inject, cleanup, status)"
    exit 1
    ;;
esac
