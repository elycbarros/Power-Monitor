#!/usr/bin/env python3
"""Gera os gráficos analíticos comparativos do estudo de caso real UCI (Maio/2007).

Gera 2 visualizações técnicas salvas em docs/images/:
1. docs/images/estudo_caso_perfil_horario.png:
   Perfil médio horário de potência (kW) comparando Dias Úteis (Seg-Sex, N=23)
   e Fins de Semana (Sáb-Dom, N=8).
2. docs/images/estudo_caso_energia_diaria.png:
   Distribuição comparativa do consumo diário (kWh/dia) com mediana, IQR e pontos individuais.

Requer matplotlib e pandas.
"""

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "data" / "medicoes_uci_2007_05.csv"
OUTPUT_DIR = BASE_DIR / "docs" / "images"


def carregar_dados_e_classificar(csv_path: Path):
    """Carrega as medições horárias e classifica por dia da semana e grupo."""
    df = pd.read_csv(csv_path)
    df["data_hora"] = pd.to_datetime(df["data_hora"])
    df["dia"] = df["data_hora"].dt.strftime("%Y-%m-%d")
    df["hora"] = df["data_hora"].dt.hour
    df["dia_semana"] = df["data_hora"].dt.weekday  # 0=Segunda ... 6=Domingo
    df["grupo"] = df["dia_semana"].apply(lambda x: "Fim de Semana" if x >= 5 else "Dias Úteis")
    return df


def gerar_grafico_perfil_horario(df: pd.DataFrame, output_path: Path):
    """Gera o gráfico comparativo do perfil médio de potência horária."""
    # Agrupamento por grupo e hora
    perfil = df.groupby(["grupo", "hora"])["potencia_kw"].agg(["mean", "std", "count"]).reset_index()

    perfil_uteis = perfil[perfil["grupo"] == "Dias Úteis"].sort_values("hora")
    perfil_fim_semana = perfil[perfil["grupo"] == "Fim de Semana"].sort_values("hora")

    horas = np.arange(24)

    plt.figure(figsize=(11, 5.5), dpi=150)

    # Dias Úteis
    plt.plot(
        horas,
        perfil_uteis["mean"],
        marker="o",
        markersize=5,
        color="#1f77b4",
        linewidth=2.2,
        label="Dias Úteis (Seg–Sex, N = 23 dias completos)",
    )

    # Fins de Semana
    plt.plot(
        horas,
        perfil_fim_semana["mean"],
        marker="s",
        markersize=5,
        color="#d62728",
        linewidth=2.2,
        label="Fins de Semana (Sáb–Dom, N = 8 dias completos)",
    )

    # Picos assinalados
    idx_pico_u = perfil_uteis["mean"].idxmax()
    h_pico_u = perfil_uteis.loc[idx_pico_u, "hora"]
    v_pico_u = perfil_uteis.loc[idx_pico_u, "mean"]

    idx_pico_fds = perfil_fim_semana["mean"].idxmax()
    h_pico_fds = perfil_fim_semana.loc[idx_pico_fds, "hora"]
    v_pico_fds = perfil_fim_semana.loc[idx_pico_fds, "mean"]

    plt.scatter([h_pico_u], [v_pico_u], color="#1f77b4", s=100, zorder=5)
    plt.scatter([h_pico_fds], [v_pico_fds], color="#d62728", s=100, zorder=5)

    plt.annotate(
        f"Pico Úteis: {v_pico_u:.2f} kW ({h_pico_u:02d}:00)",
        xy=(h_pico_u, v_pico_u),
        xytext=(h_pico_u - 4, v_pico_u + 0.18),
        arrowprops=dict(arrowstyle="->", color="#1f77b4", lw=1.2),
        fontsize=9,
        fontweight="bold",
        color="#1f77b4",
    )

    plt.annotate(
        f"Pico Fim de Semana: {v_pico_fds:.2f} kW ({h_pico_fds:02d}:00)",
        xy=(h_pico_fds, v_pico_fds),
        xytext=(h_pico_fds - 5.5, v_pico_fds + 0.22),
        arrowprops=dict(arrowstyle="->", color="#d62728", lw=1.2),
        fontsize=9,
        fontweight="bold",
        color="#d62728",
    )

    plt.title(
        "Perfil Médio Horário de Potência Ativa: Dias Úteis vs. Fins de Semana\n"
        "Residência Individual (Sceaux, França) — Maio/2007 (Fonte: UCI / Hebrail & Berard, 2006)",
        fontsize=11,
        fontweight="bold",
        pad=14,
    )
    plt.xlabel("Hora do Dia (00:00 às 23:00)", fontsize=10, labelpad=8)
    plt.ylabel("Potência Ativa Média (kW)", fontsize=10, labelpad=8)
    plt.xticks(horas, [f"{h:02d}h" for h in horas])
    plt.xlim(-0.5, 23.5)
    plt.ylim(0, 2.7)
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.legend(loc="upper left", framealpha=0.95, fontsize=9.5)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"-> Gráfico 1 salvo com sucesso: {output_path}")


def gerar_grafico_energia_diaria(df: pd.DataFrame, output_path: Path):
    """Gera o gráfico boxplot/dispersão comparando o consumo diário de energia."""
    # Agrupar energia por dia (soma das 24 horas * 1.0h = kWh)
    diario = df.groupby(["dia", "grupo"])["potencia_kw"].sum().reset_index()
    diario.rename(columns={"potencia_kw": "energia_kwh"}, inplace=True)

    dados_uteis = diario[diario["grupo"] == "Dias Úteis"]["energia_kwh"].values
    dados_fim_semana = diario[diario["grupo"] == "Fim de Semana"]["energia_kwh"].values

    med_u = float(np.median(dados_uteis))
    q25_u = float(np.percentile(dados_uteis, 25))
    q75_u = float(np.percentile(dados_uteis, 75))
    iqr_u = q75_u - q25_u
    media_u = float(np.mean(dados_uteis))

    med_fds = float(np.median(dados_fim_semana))
    q25_fds = float(np.percentile(dados_fim_semana, 25))
    q75_fds = float(np.percentile(dados_fim_semana, 75))
    iqr_fds = q75_fds - q25_fds
    media_fds = float(np.mean(dados_fim_semana))

    fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=150)

    # Boxplot
    bp = ax.boxplot(
        [dados_uteis, dados_fim_semana],
        positions=[1, 2],
        widths=0.45,
        patch_artist=True,
        showmeans=True,
        meanline=True,
        medianprops=dict(color="black", linewidth=2),
        meanprops=dict(color="blue", linewidth=1.5, linestyle="--"),
    )

    cores = ["#a6c8e0", "#f2a8a8"]
    for patch, cor in zip(bp["boxes"], cores):
        patch.set_facecolor(cor)
        patch.set_alpha(0.7)

    # Adicionar dispersão dos pontos reais (jitter)
    np.random.seed(42)
    jitter_u = np.random.normal(0, 0.04, size=len(dados_uteis))
    jitter_fds = np.random.normal(0, 0.04, size=len(dados_fim_semana))

    ax.scatter([1 + j for j in jitter_u], dados_uteis, color="#1f77b4", alpha=0.8, s=40, zorder=4, label="Dias Úteis (N=23)")
    ax.scatter([2 + j for j in jitter_fds], dados_fim_semana, color="#d62728", alpha=0.8, s=40, zorder=4, label="Fins de Semana (N=8)")

    # Texto estatístico descritivo nas caixas
    texto_u = (
        f"Média: {media_u:.2f} kWh/dia\n"
        f"Mediana: {med_u:.2f} kWh/dia\n"
        f"Q25: {q25_u:.2f} | Q75: {q75_u:.2f}\n"
        f"IQR: {iqr_u:.2f} kWh/dia"
    )
    texto_fds = (
        f"Média: {media_fds:.2f} kWh/dia\n"
        f"Mediana: {med_fds:.2f} kWh/dia\n"
        f"Q25: {q25_fds:.2f} | Q75: {q75_fds:.2f}\n"
        f"IQR: {iqr_fds:.2f} kWh/dia"
    )

    ax.text(1, 8.5, texto_u, ha="center", va="bottom", fontsize=8.5, bbox=dict(boxstyle="round,pad=0.4", facecolor="#eef4f8", alpha=0.9))
    ax.text(2, 8.5, texto_fds, ha="center", va="bottom", fontsize=8.5, bbox=dict(boxstyle="round,pad=0.4", facecolor="#fdeeee", alpha=0.9))

    ax.set_xticks([1, 2])
    ax.set_xticklabels(["Dias Úteis\n(Seg–Sex, N = 23)", "Fins de Semana\n(Sáb–Dom, N = 8)"], fontsize=10, fontweight="bold")
    ax.set_ylabel("Energia Consumida por Dia Completo (kWh/dia)", fontsize=10, labelpad=8)
    ax.set_ylim(6, 40)
    ax.grid(True, linestyle=":", alpha=0.6, axis="y")

    plt.title(
        "Comparação da Energia Diária: Dias Úteis vs. Fins de Semana\n"
        "Residência Individual (Sceaux, França) — Maio/2007 (Fonte: UCI / Hebrail & Berard, 2006)",
        fontsize=11,
        fontweight="bold",
        pad=14,
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"-> Gráfico 2 salvo com sucesso: {output_path}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Arquivo CSV {CSV_PATH} não encontrado. Execute scripts/preparar_estudo_caso_uci.py primeiro.")

    print(f"-> Carregando dados de {CSV_PATH}...")
    df = carregar_dados_e_classificar(CSV_PATH)

    grafico_perfil = OUTPUT_DIR / "estudo_caso_perfil_horario.png"
    grafico_energia = OUTPUT_DIR / "estudo_caso_energia_diaria.png"

    gerar_grafico_perfil_horario(df, grafico_perfil)
    gerar_grafico_energia_diaria(df, grafico_energia)
    print("-> Geração de gráficos concluída com sucesso!")


if __name__ == "__main__":
    main()
