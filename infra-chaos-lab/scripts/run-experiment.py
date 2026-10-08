#!/usr/bin/env python3
"""
==============================================================================
run-experiment.py
End-to-End Orchestrator für das GitOps-Resilienz-Experiment
Führt das vollständige Experiment automatisiert durch:
1. Prüft Konnektivität zur EC2-Instanz (IP aus Terraform)
2. Kopiert & startet Störungsskript (inject-iptables.sh) via SSH
3. Misst Transitionszeiten (Healthy -> Progressing/Degraded -> Healthy)
4. Berechnet die exakte MTTR (Mean Time to Recovery)
5. Exportiert Prometheus-Metriken (CSV) & generiert wissenschaftliche Plots (PDF/PNG)
==============================================================================
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime


def get_tf_output(output_name: str, tf_dir: str) -> str:
    """Liest einen Output-Wert aus Terraform."""
    try:
        res = subprocess.run(
            ["terraform", "output", "-raw", output_name],
            cwd=tf_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception as exc:
        print(f"[WARN] Konnte '{output_name}' nicht aus Terraform lesen: {exc}")
    return ""


def run_ssh_command(host: str, key_path: str, command: str, check: bool = True) -> subprocess.CompletedProcess:
    """Führt einen Befehl per SSH auf der EC2-Instanz aus."""
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-i", key_path,
        f"ubuntu@{host}",
        command,
    ]
    return subprocess.run(ssh_cmd, capture_output=True, text=True, check=check)


def copy_file_via_scp(host: str, key_path: str, local_path: str, remote_path: str) -> None:
    """Überträgt eine Datei per SCP auf die EC2-Instanz."""
    scp_cmd = [
        "scp",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-i", key_path,
        local_path,
        f"ubuntu@{host}:{remote_path}",
    ]
    subprocess.run(scp_cmd, check=True)


def get_argocd_app_status(host: str, key_path: str, app_name: str = "baseline-workload-app") -> tuple:
    """Liest Sync- und Health-Status einer ArgoCD Application per kubectl aus."""
    cmd = (
        f"sudo kubectl -n argocd get application {app_name} "
        f"-o jsonpath='{{.status.sync.status}}|{{.status.health.status}}' 2>/dev/null || echo 'Unknown|Unknown'"
    )
    res = run_ssh_command(host, key_path, cmd, check=False)
    parts = res.stdout.strip().split("|")
    if len(parts) == 2:
        return parts[0], parts[1]
    return "Unknown", "Unknown"


def main():
    parser = argparse.ArgumentParser(description="Automatisiertes GitOps-Chaos-Experiment.")
    parser.add_argument("--host", default=None, help="EC2 Public IP (Standard: aus Terraform)")
    parser.add_argument("--ssh-key", default=os.path.expanduser("~/.ssh/id_ed25519"), help="Pfad zum SSH Private Key")
    parser.add_argument("--duration", type=int, default=120, help="Dauer der Störung in Sekunden (Standard: 120)")
    parser.add_argument("--probability", type=float, default=0.40, help="Paketverlust-Rate (Standard: 0.40 = 40%)")
    parser.add_argument("--baseline-wait", type=int, default=30, help="Vorlaufzeit Normalbetrieb in Sekunden (Standard: 30)")
    args = parser.parse_args()

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    tf_dir = os.path.join(base_dir, "terraform")
    scripts_dir = os.path.join(base_dir, "scripts")
    analysis_dir = os.path.join(base_dir, "analysis")

    host = args.host or get_tf_output("instance_public_ip", tf_dir)
    if not host:
        print("[FEHLER] Keine EC2-Host-IP ermittelt. Läuft das Cluster? (terraform apply)", file=sys.stderr)
        sys.exit(1)

    print("=================================================================")
    print("      GITOPS RESILIENZ- & RECONCILIATION-EXPERIMENT")
    print("=================================================================")
    print(f"Ziel-Host:               {host}")
    print(f"Störungsdauer:           {args.duration}s")
    print(f"Paketverlust:            {int(args.probability * 100)}%")
    print(f"SSH-Schlüssel:           {args.ssh_key}")
    print("-----------------------------------------------------------------")

    # 1. Konnektivität & Vorbereitung
    print("\n[PHASE 0] Prüfe Verbindung & übertrage Störungs-Skript...")
    inject_script = os.path.join(scripts_dir, "inject-iptables.sh")
    copy_file_via_scp(host, args.ssh_key, inject_script, "/home/ubuntu/inject-iptables.sh")
    run_ssh_command(host, args.ssh_key, "chmod +x /home/ubuntu/inject-iptables.sh")
    print("[OK] inject-iptables.sh liegt auf der Instanz bereit.")

    # Status vor dem Test prüfen
    sync_stat, health_stat = get_argocd_app_status(host, args.ssh_key)
    print(f"[STATUS INITIAL] Sync: {sync_stat} | Health: {health_stat}")

    # 2. Vorlaufzeit (Baseline)
    print(f"\n[PHASE 1] Aufzeichnung Normalbetrieb (Vorlaufzeit {args.baseline_wait}s)...")
    time.sleep(args.baseline_wait)

    # 3. Störung injizieren
    start_chaos_time = time.time()
    print(f"\n[PHASE 2] Injiziere transiente Netzwerkstörung ({int(args.probability * 100)}% Drop für {args.duration}s)...")
    # Startet im Hintergrund auf EC2
    chaos_cmd = (
        f"sudo PROBABILITY={args.probability} DURATION={args.duration} "
        f"/home/ubuntu/inject-iptables.sh inject > /tmp/chaos.log 2>&1 &"
    )
    run_ssh_command(host, args.ssh_key, chaos_cmd)

    degraded_seen = False
    degraded_timestamp = None
    recovered_timestamp = None

    # Beobachte Cluster während der Störung und danach
    monitor_max_sec = args.duration + 180  # Dauer + 3 Minuten Puffer für Heilung
    poll_start = time.time()

    print("\nBeobachte ArgoCD State Machine & Reconciliation Loop:")
    while time.time() - poll_start < monitor_max_sec:
        elapsed = int(time.time() - poll_start)
        s_stat, h_stat = get_argocd_app_status(host, args.ssh_key)
        now_str = datetime.now().strftime("%H:%M:%S")

        print(f"  [{now_str} +{elapsed:03d}s] App Status -> Sync: {s_stat:<12} | Health: {h_stat:<12}")

        if (s_stat != "Synced" or h_stat != "Healthy") and not degraded_seen:
            degraded_seen = True
            degraded_timestamp = time.time()
            print(f"  --> \033[1;33m[EVENT] Transienter Zustand erreicht ({s_stat}/{h_stat})\033[0m")

        # Wenn Störungsfenster vorbei ist und wieder healthy
        if elapsed > args.duration and degraded_seen and s_stat == "Synced" and h_stat == "Healthy":
            recovered_timestamp = time.time()
            print(f"  --> \033[1;32m[EVENT] Self-Healing erfolgreich! Cluster wieder 'Synced' & 'Healthy'\033[0m")
            break

        time.sleep(5)

    # 4. MTTR Auswertung
    print("\n-----------------------------------------------------------------")
    print("                     EXPERIMENT-ERGEBNIS")
    print("-----------------------------------------------------------------")
    if degraded_timestamp and recovered_timestamp:
        mttr_sec = recovered_timestamp - (start_chaos_time + args.duration)
        total_degraded_time = recovered_timestamp - degraded_timestamp
        print(f"Dauer des transienten Zustands (Dwell Time): {total_degraded_time:.1f} Sekunden")
        print(f"Gemessene Mean Time to Recovery (MTTR):      {mttr_sec:.1f} Sekunden nach Fehlerbehebung")
    else:
        print("[HINWEIS] Keine vollständige Heilungs-Zyklus-Erkennung im Zeitfenster.")

    # 5. Metriken exportieren & Plots generieren
    print("\n[PHASE 3] Ziehe Prometheus-Metriken...")
    export_script = os.path.join(scripts_dir, "export-metrics.py")
    subprocess.run([sys.executable, export_script, "--host", host, "--minutes", "15"], check=True)

    print("\n[PHASE 4] Generiere wissenschaftliche Diagramme...")
    plot_script = os.path.join(analysis_dir, "plot-results.py")
    subprocess.run([sys.executable, plot_script], check=True)

    print("\n=================================================================")
    print("[OK] Experiment vollständig abgeschlossen! Diagramme & CSV bereit.")
    print("=================================================================")


if __name__ == "__main__":
    main()
