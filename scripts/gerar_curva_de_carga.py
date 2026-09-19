#!/usr/bin/env python3
"""Gera o gráfico da curva de carga semanal a partir de data/medicoes.csv.

Salva a imagem em docs/images/curva_de_carga.png para inclusão na documentação.
Requer matplotlib (declarado em requirements-dev.txt).

Limitação e premissa de escopo:
Este script destina-se especificamente ao conjunto de exemplo completo e contínuo
(data/medicoes.csv, 168 horas contínuas sem lacunas). Para séries arbitrárias com
lacunas temporais, um gráfico contínuo linear não deve ser utilizado sem tratamento
de descontinuidade (para evitar traçar linhas ligando pontos separados por intervalos ausentes).
"""

from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "data" / "medicoes.csv"
OUTPUT_IMG = BASE_DIR / "docs" / "images" / "curva_de_carga.png"

# Mapeamento de dias da semana em português brasileiro
DIAS_SEMANA_PT = {
    0: "Seg",
    1: "Ter",
    2: "Qua",
    3: "Qui",
    4: "Sex",
    5: "Sáb",
    6: "Dom",
}


def gerar_grafico():
    OUTPUT_IMG.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(CSV_PATH)
    df["data_hora"] = pd.to_datetime(df["data_hora"])
    df = df.sort_values("data_hora").reset_index(drop=True)

    pot_media = float(df["potencia_kw"].mean())
    # Desempate determinístico para o pico de demanda (maior potência, menor data_hora)
    df_pico = df.sort_values(["potencia_kw", "data_hora"], ascending=[False, True])
    pico_row = df_pico.iloc[0]

    # Formatação com vírgula no padrão brasileiro
    media_fmt = f"{pot_media:.2f}".replace(".", ",")
    pico_fmt = f"{float(pico_row['potencia_kw']):.2f}".replace(".", ",")
    pico_data_fmt = pico_row["data_hora"].strftime("%d/%m às %H:%M")

    plt.figure(figsize=(12, 5), dpi=150)
    plt.plot(
        df["data_hora"],
        df["potencia_kw"],
        color="#1f77b4",
        linewidth=1.5,
        label="Potência Média Horária (kW)",
    )

    # Linha horizontal de potência média semanal
    plt.axhline(
        y=pot_media,
        color="#2ca02c",
        linestyle="--",
        linewidth=1.2,
        label=f"Potência Média Semanal: {media_fmt} kW",
    )

    # Ponto do pico de demanda
    plt.plot(
        pico_row["data_hora"],
        pico_row["potencia_kw"],
        marker="o",
        color="#d62728",
        markersize=6,
        label=f"Pico de Demanda: {pico_fmt} kW ({pico_data_fmt})",
    )

    plt.title(
        "Curva de Carga Horária Semanal — PowerMonitor\n(Dados Sintéticos para Fins Didáticos)",
        fontsize=12,
        fontweight="bold",
        pad=12,
    )
    plt.xlabel("Data e Horário", fontsize=10, labelpad=8)
    plt.ylabel("Potência Ativa Média (kW)", fontsize=10, labelpad=8)

    # Definir ticks diários em português
    ax = plt.gca()
    dias_unicos = pd.date_range(df["data_hora"].min().floor("D"), df["data_hora"].max().ceil("D"), freq="1D")
    ax.set_xticks(dias_unicos)
    rotulos_x = [f"{d.strftime('%d/%m')}\n{DIAS_SEMANA_PT[d.weekday()]}" for d in dias_unicos]
    ax.set_xticklabels(rotulos_x)
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[6, 12, 18]))

    # Limites dos eixos e grid
    plt.ylim(0, 32)
    plt.grid(True, linestyle=":", alpha=0.6)

    # Legenda posicionada em 'upper left' para não sobrepor o pico na quarta-feira (05/08)
    plt.legend(loc="upper left", framealpha=0.92, fontsize=9)
    plt.tight_layout()

    plt.savefig(OUTPUT_IMG, format="png")
    plt.close()
    print(f"Gráfico gerado com sucesso em: {OUTPUT_IMG}")


if __name__ == "__main__":
    gerar_grafico()
