#!/usr/bin/env python3
"""
==============================================================================
plot-results.py
Wissenschaftlicher Diagramm-Generator für die Seminar- und Bachelorarbeit
Liest exportierte CSV-Dateien ein und erzeugt publikationsreife Vektorgrafiken
(PDF & PNG) nach IEEE-Standard für wissenschaftliche Arbeiten.
==============================================================================
"""

import argparse
import glob
import os
import sys
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd


# Wissenschaftliches Plot-Styling
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.titlesize": 13,
    "lines.linewidth": 1.5,
    "grid.alpha": 0.4,
    "grid.linestyle": "--",
})


def plot_reconciliation_latency(df: pd.DataFrame, output_dir: str, prefix: str):
    """Plot 1: Verteilung und Zeitverlauf der Reconciliation-Latenz (Median & p95)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4), gridspec_kw={"width_ratios": [2.5, 1]})

    # Zeitverlauf
    if "reconcile_duration_p95_sec" in df.columns:
        ax1.plot(df.index, df["reconcile_duration_p95_sec"], label="Reconciliation Latenz (p95)", color="#d95f02")
    if "reconcile_duration_median_sec" in df.columns:
        ax1.plot(df.index, df["reconcile_duration_median_sec"], label="Reconciliation Latenz (Median)", color="#1b9e77")

    ax1.set_title("A: Zeitverlauf der Abgleich-Latenz (Reconciliation Loop)")
    ax1.set_xlabel("Zeitpunkt (UTC)")
    ax1.set_ylabel("Latenz [Sekunden]")
    ax1.grid(True)
    ax1.legend(loc="upper left")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))

    # Boxplot / Verteilung
    plot_data = []
    labels = []
    if "reconcile_duration_median_sec" in df.columns:
        plot_data.append(df["reconcile_duration_median_sec"].dropna())
        labels.append("Median")
    if "reconcile_duration_p95_sec" in df.columns:
        plot_data.append(df["reconcile_duration_p95_sec"].dropna())
        labels.append("p95")

    if plot_data:
        bp = ax2.boxplot(plot_data, labels=labels, patch_artist=True)
        colors = ["#1b9e77", "#d95f02"]
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        ax2.set_title("B: Latenz-Streuung")
        ax2.set_ylabel("Latenz [s]")
        ax2.grid(True)

    plt.tight_layout()
    for ext in ["pdf", "png"]:
        out_file = os.path.join(output_dir, f"{prefix}_latency_distribution.{ext}")
        plt.savefig(out_file, dpi=300)
    plt.close()
    print(f"  [OK] Diagramm 1 generiert: {prefix}_latency_distribution (PDF & PNG)")


def plot_controller_resources(df: pd.DataFrame, output_dir: str, prefix: str):
    """Plot 2: Ressourcenverbrauch des Controllers (CPU & RAM vs. Limit)."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5), sharex=True)

    # RAM (in MiB)
    if "controller_memory_bytes" in df.columns:
        ram_mib = df["controller_memory_bytes"] / (1024 * 1024)
        ax1.plot(df.index, ram_mib, label="Controller RAM (Working Set)", color="#7570b3")
        # Referenzlinie: Konfiguriertes Limit aus Helm (512 MiB)
        ax1.axhline(y=512, color="red", linestyle=":", label="OOM Schwellenwert / Limit (512 MiB)")
        ax1.set_ylabel("RAM [MiB]")
        ax1.set_title("A: Arbeitsspeicher-Verlauf (OOM-Risiko-Quantifizierung)")
        ax1.grid(True)
        ax1.legend(loc="upper left")

    # CPU (in Millicores)
    if "controller_cpu_cores" in df.columns:
        cpu_mcores = df["controller_cpu_cores"] * 1000
        ax2.plot(df.index, cpu_mcores, label="Controller CPU Last", color="#e7298a")
        ax2.set_ylabel("CPU [mCores]")
        ax2.set_xlabel("Zeitpunkt (UTC)")
        ax2.set_title("B: Rechenlast bei Synchronisation & Retries")
        ax2.grid(True)
        ax2.legend(loc="upper left")
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))

    plt.tight_layout()
    for ext in ["pdf", "png"]:
        out_file = os.path.join(output_dir, f"{prefix}_controller_resources.{ext}")
        plt.savefig(out_file, dpi=300)
    plt.close()
    print(f"  [OK] Diagramm 2 generiert: {prefix}_controller_resources (PDF & PNG)")


def plot_resilience_multi_timeline(df: pd.DataFrame, output_dir: str, prefix: str):
    """Plot 3: Vollständiger Störungsverlauf (Latenz, Sync-Fehler und TCP Retransmits)."""
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 7), sharex=True)

    # 1. Latenz
    if "reconcile_duration_p95_sec" in df.columns:
        ax1.plot(df.index, df["reconcile_duration_p95_sec"], label="Reconcile p95", color="#d95f02")
    ax1.set_ylabel("Latenz [s]")
    ax1.set_title("Phasenverlauf: Normalbetrieb vs. Transiente Störung vs. Erholung")
    ax1.grid(True)
    ax1.legend(loc="upper left")

    # 2. Sync-Raten (Erfolg vs. Fehler)
    if "sync_succeeded_rate" in df.columns:
        ax2.plot(df.index, df["sync_succeeded_rate"], label="Sync Erfolge / s", color="#1b9e77")
    if "sync_failed_rate" in df.columns:
        ax2.plot(df.index, df["sync_failed_rate"], label="Sync Fehler / s", color="#e41a1c")
    ax2.set_ylabel("Ops / Sekunde")
    ax2.grid(True)
    ax2.legend(loc="upper left")

    # 3. Kernel TCP Retransmissions
    if "tcp_retrans_rate" in df.columns:
        ax3.plot(df.index, df["tcp_retrans_rate"], label="TCP Retransmissions / s (Kernel Netstat)", color="#666666")
    ax3.set_ylabel("Retrans / s")
    ax3.set_xlabel("Zeitpunkt (UTC)")
    ax3.grid(True)
    ax3.legend(loc="upper left")
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))

    plt.tight_layout()
    for ext in ["pdf", "png"]:
        out_file = os.path.join(output_dir, f"{prefix}_resilience_timeline.{ext}")
        plt.savefig(out_file, dpi=300)
    plt.close()
    print(f"  [OK] Diagramm 3 generiert: {prefix}_resilience_timeline (PDF & PNG)")


def main():
    parser = argparse.ArgumentParser(
        description="Erzeugt wissenschaftliche Publikationsdiagramme aus exportierten CSV-Daten."
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Pfad zur Messdaten-CSV-Datei (Standard: neueste Datei in infra-chaos-lab/data/)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Ausgabeverzeichnis für Grafiken (Standard: infra-chaos-lab/analysis/plots/)",
    )
    args = parser.parse_args()

    # CSV-Datei bestimmen
    if args.input:
        csv_file = args.input
    else:
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
        csv_files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
        if not csv_files:
            print(f"[FEHLER] Keine CSV-Dateien in '{data_dir}' gefunden. Bitte zuerst export-metrics.py ausführen!", file=sys.stderr)
            sys.exit(1)
        csv_file = csv_files[-1]  # Neueste Datei nehmen

    print(f"Lese Messdaten aus: {csv_file}")
    df = pd.read_csv(csv_file, parse_dates=["timestamp"], index_col="timestamp")

    # Ausgabeverzeichnis
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "plots"))
    os.makedirs(output_dir, exist_ok=True)

    prefix = os.path.splitext(os.path.basename(csv_file))[0]

    print("\nGeneriere wissenschaftliche Diagramme...")
    plot_reconciliation_latency(df, output_dir, prefix)
    plot_controller_resources(df, output_dir, prefix)
    plot_resilience_multi_timeline(df, output_dir, prefix)

    print(f"\n[OK] Alle Grafiken erfolgreich gespeichert in:\n     {output_dir}")


if __name__ == "__main__":
    main()
