#!/usr/bin/env python3
"""
==============================================================================
export-metrics.py
Wissenschaftlicher Metrik-Extraktor für das GitOps-Resilienz-Messframework
Zieht Zeitreihendaten per PromQL aus Prometheus und exportiert sie als CSV.
==============================================================================
"""

import argparse
import datetime
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional
import requests
import pandas as pd


# Definition der Kernmetriken aus unserem wissenschaftlichen Kriterienkatalog
PROMETHEUS_QUERIES: Dict[str, str] = {
    # 1. Resilienz & Latenz
    "reconcile_duration_p95_sec": (
        'histogram_quantile(0.95, sum(rate(argocd_app_reconcile_duration_seconds_bucket[1m])) by (le))'
    ),
    "reconcile_duration_median_sec": (
        'histogram_quantile(0.50, sum(rate(argocd_app_reconcile_duration_seconds_bucket[1m])) by (le))'
    ),
    # 2. Integrität & Fehlerraten
    "sync_succeeded_rate": 'sum(rate(argocd_app_sync_total{phase="Succeeded"}[1m])) or vector(0)',
    "sync_failed_rate": 'sum(rate(argocd_app_sync_total{phase=~"Failed|Error"}[1m])) or vector(0)',
    # 3. Ressourcenlast der Control Plane (Sättigung & OOM-Risiko)
    "controller_memory_bytes": (
        'sum(container_memory_working_set_bytes{container=~".*application-controller.*|controller"})'
    ),
    "controller_cpu_cores": (
        'sum(rate(container_cpu_usage_seconds_total{container=~".*application-controller.*|controller"}[1m]))'
    ),
    # 4. Kernel-Netzwerk-Overhead
    "tcp_retrans_rate": 'rate(node_netstat_Tcp_RetransSegs[1m]) or vector(0)',
}


def get_default_host() -> str:
    """Versucht dynamisch die EC2 Public IP aus Terraform Output zu lesen."""
    tf_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "terraform"))
    if os.path.isdir(tf_dir):
        try:
            res = subprocess.run(
                ["terraform", "output", "-raw", "instance_public_ip"],
                cwd=tf_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass
    return os.environ.get("PROMETHEUS_HOST", "localhost")


def query_prometheus_range(
    base_url: str,
    query: str,
    start_ts: float,
    end_ts: float,
    step: str = "5s",
) -> List[tuple]:
    """Fragt die Prometheus HTTP query_range API ab."""
    url = f"{base_url}/api/v1/query_range"
    params = {
        "query": query,
        "start": start_ts,
        "end": end_ts,
        "step": step,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            return []
        
        results = data.get("data", {}).get("result", [])
        if not results:
            return []

        # Erstes Ergebnis extrahieren (bei aggregierten Queries)
        values = results[0].get("values", [])
        return [(float(v[0]), float(v[1])) for v in values]
    except Exception as exc:
        print(f"  [WARN] Fehler bei Query '{query}': {exc}", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Exportiert wissenschaftliche Messdaten aus Prometheus als CSV."
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Prometheus Host / IP (Standard: automatische Erkennung via Terraform)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=30090,
        help="Prometheus NodePort (Standard: 30090)",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        default=30,
        help="Dauer des Erhebungszeitfensters in Minuten bis jetzt (Standard: 30)",
    )
    parser.add_argument(
        "--step",
        default="5s",
        help="Messauflösung / Scrape-Intervall (Standard: 5s)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Ausgabe-Pfad der CSV-Datei (Standard: infra-chaos-lab/data/experiment_YYYYMMDD_HHMMSS.csv)",
    )
    args = parser.parse_args()

    host = args.host or get_default_host()
    base_url = f"http://{host}:{args.port}"
    print(f"=== Prometheus Verbindung: {base_url} ===")

    # Zeitfenster berechnen
    now = time.time()
    start_ts = now - (args.minutes * 60)
    end_ts = now

    start_iso = datetime.datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S")
    end_iso = datetime.datetime.fromtimestamp(end_ts).strftime("%Y-%m-%d %H:%M:%S")
    print(f"Erhebungszeitraum: {start_iso} bis {end_iso} ({args.minutes} Minuten)")

    # Alle Metriken nacheinander abfragen
    series_dict = {}
    timestamps = None

    print("\nZiehe PromQL-Zeitreihen...")
    for metric_name, query_str in PROMETHEUS_QUERIES.items():
        print(f"  -> {metric_name}...")
        data_points = query_prometheus_range(base_url, query_str, start_ts, end_ts, step=args.step)
        if data_points:
            ts_list, val_list = zip(*data_points)
            if timestamps is None:
                timestamps = ts_list
            series_dict[metric_name] = pd.Series(val_list, index=ts_list)
        else:
            print(f"     [INFO] Keine Messwerte vorhanden für '{metric_name}'.")

    if not series_dict:
        print("\n[FEHLER] Es konnten keine Metriken abgerufen werden. Läuft Prometheus?", file=sys.stderr)
        sys.exit(1)

    # DataFrame zusammensetzen
    df = pd.DataFrame(series_dict)
    df.index = pd.to_datetime(df.index, unit="s")
    df.index.name = "timestamp"

    # Fehlende Werte interpolieren / füllen
    df = df.ffill().fillna(0)

    # Speicherpfad bestimmen
    if args.output:
        out_path = args.output
    else:
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
        os.makedirs(data_dir, exist_ok=True)
        out_path = os.path.join(data_dir, f"metrics_{timestamp_str}.csv")

    df.to_csv(out_path)
    print(f"\n[OK] {len(df)} Messpunkte erfolgreich exportiert nach:")
    print(f"     {out_path}")

    # Statistische Kurzübersicht (Deskriptive Statistik)
    print("\n=== Deskriptive Statistik der Messreihe ===")
    summary = df.describe().T[["mean", "std", "min", "50%", "max"]]
    summary.rename(columns={"50%": "median"}, inplace=True)
    print(summary.to_string())


if __name__ == "__main__":
    main()
