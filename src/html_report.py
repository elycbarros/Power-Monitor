"""Módulo de geração de relatório visual em HTML estático e autocontido do PowerMonitor.

Responsabilidades deste módulo (Camada de Visualização):
- Gerar gráficos analíticos embutidos diretamente em Base64 usando Matplotlib (backend Agg):
  1. Curva de Carga com interrupção estrita de linha nos intervalos ausentes;
  2. Gráfico de Consumo Diário cronológico destacando dias parciais e dia de maior consumo;
  3. Mapa de Calor (Dia × Horário) diferenciando dados ausentes e potência zero válida.
- Montar documento HTML5 estático, offline e sem dependências externas (sem CDN, fontes ou scripts remotos).
- Aplicar formatação numérica brasileira e escape defensivo contra injeção de tags dinâmicas.
- Persistir o arquivo de forma atômica no sistema de arquivos.

Conceitos de Programação e Engenharia de Software aplicados:
- 'Zero External Dependencies': Utiliza apenas a biblioteca padrão do Python, Pandas e Matplotlib,
  garantindo funcionamento autônomo sem conexão à internet.
- 'Headless Matplotlib Rendering': Uso do backend não interativo 'Agg' com context manager ou fechamento
  explícito (`plt.close(fig)`) para evitar retenção indevida de memória RAM em execuções sucessivas.
- 'Atomic File Write': Escrita em arquivo temporário seguida de substituição atômica (`replace`),
  evitando arquivos corrompidos ou incompletos em caso de interrupção abrupta do processo.
- 'Data Security & XSS Prevention': Todas as strings dinâmicas inseridas no template são escapadas via `html.escape`.
"""

import base64
from datetime import datetime
import html
import io
import math
from pathlib import Path
import time
from typing import Optional, Dict, Any, Union, List

import matplotlib
matplotlib.use("Agg")  # Backend não interativo para geração headless de imagens
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from src.analysis import IndicadoresCompletosDict, gerar_sintese_executiva
from src.report import formatar_numero_br


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


def _fig_para_base64(fig: plt.Figure) -> str:
    """Converte uma figura do Matplotlib em string Data URI base64 PNG e encerra a figura."""
    try:
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=140, bbox_inches="tight")
        buffer.seek(0)
        b64_dados = base64.b64encode(buffer.read()).decode("utf-8")
        return f"data:image/png;base64,{b64_dados}"
    finally:
        plt.close(fig)


def gerar_curva_de_carga_base64(
    df_historico: pd.DataFrame,
    intervalo_horas: float,
    demanda_maxima: float,
    horario_max: Optional[str],
    potencia_media: float,
) -> str:
    """Gera a curva de carga temporal com interrupção de linha nas lacunas e retorna imagem Base64.

    Rigor Técnico e Metrológico:
    - Reindexa o DataFrame em uma grade temporal contínua com passo de `intervalo_horas`.
    - Intervalos ausentes recebem `np.nan`, forçando o Matplotlib a quebrar a linha contínua.
    - Isso impede a ilusão visual de que houve medição durante períodos de corte de energia ou perda de sinal.
    """
    if df_historico.empty or "data_hora" not in df_historico.columns or "potencia_kw" not in df_historico.columns:
        return ""

    df_temp = df_historico.copy()
    df_temp["data_hora"] = pd.to_datetime(df_temp["data_hora"])
    df_temp = df_temp.sort_values("data_hora").reset_index(drop=True)

    t_min = df_temp["data_hora"].iloc[0]
    t_max = df_temp["data_hora"].iloc[-1]

    # Cria grade teórica contínua
    minutos_passo = int(round(intervalo_horas * 60))
    freq_str = f"{minutos_passo}min"
    grid_completa = pd.date_range(t_min, t_max, freq=freq_str)

    df_grid = pd.DataFrame({"data_hora": grid_completa})
    df_plot = pd.merge(df_grid, df_temp[["data_hora", "potencia_kw"]], on="data_hora", how="left")

    fig, ax = plt.subplots(figsize=(11, 4.5), dpi=140)

    # 1. Curva de potência ativa média no intervalo
    label_curva = (
        "Potência Média Horária (kW)"
        if intervalo_horas == 1.0
        else f"Potência Média ({minutos_passo} min) (kW)"
    )
    ax.plot(
        df_plot["data_hora"],
        df_plot["potencia_kw"],
        color="#1d4ed8",
        linewidth=1.5,
        label=label_curva,
        zorder=2,
    )

    # 2. Linha de referência da potência média do histórico
    if potencia_media > 0:
        ax.axhline(
            y=potencia_media,
            color="#16a34a",
            linestyle="--",
            linewidth=1.2,
            label=f"Potência Média: {formatar_numero_br(potencia_media, 2)} kW",
            zorder=3,
        )

    # 3. Ponto de pico de demanda
    if demanda_maxima > 0 and horario_max:
        try:
            dt_pico = pd.to_datetime(horario_max)
            rotulo_pico = (
                f"Pico: {formatar_numero_br(demanda_maxima, 2)} kW ({dt_pico.strftime('%d/%m às %H:%M')})"
            )
            ax.plot(
                dt_pico,
                demanda_maxima,
                marker="o",
                markersize=7,
                color="#dc2626",
                label=rotulo_pico,
                zorder=4,
            )
        except Exception:
            pass

    # Formatação de Eixos
    ax.set_ylabel("Potência Ativa Média (kW)", fontsize=9, fontweight="bold", color="#1e293b", labelpad=8)
    ax.set_xlabel("Data e Horário", fontsize=9, fontweight="bold", color="#1e293b", labelpad=8)

    # Ajuste adaptativo de marcas no eixo X
    delta_dias = (t_max - t_min).total_seconds() / 86400.0
    if delta_dias <= 2:
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m\n%H:%M"))
    elif delta_dias <= 8:
        dias_unicos = pd.date_range(t_min.floor("D"), t_max.ceil("D"), freq="1D")
        ax.set_xticks(dias_unicos)
        ax.set_xticklabels([f"{d.strftime('%d/%m')}\n{DIAS_SEMANA_PT.get(d.weekday(), '')}" for d in dias_unicos])
        ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[6, 12, 18]))
    else:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, int(delta_dias / 8))))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))

    ax.set_ylim(bottom=0, top=max(10.0, demanda_maxima * 1.18))
    ax.grid(True, linestyle=":", alpha=0.6, color="#cbd5e1", zorder=1)
    ax.tick_params(axis="both", which="major", labelsize=8, colors="#334155")

    # Legenda fora do gráfico para não obstruir medições
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(0.0, 1.15),
        ncol=3,
        frameon=True,
        facecolor="#f8fafc",
        edgecolor="#cbd5e1",
        fontsize=8.5,
    )

    return _fig_para_base64(fig)


def gerar_grafico_consumo_diario_base64(
    df_diario: pd.DataFrame,
    dia_maior_consumo: Optional[str],
) -> str:
    """Gera gráfico de barras do consumo diário ordenado cronologicamente e retorna imagem Base64.

    Rigor Técnico:
    - Diferencia dias completos (24h OK) de dias parciais (< 24h) com cores e hachuras distintas.
    - Destaca o dia de maior consumo com cor de destaque.
    - Exibe a participação percentual calculada sobre a energia total registrada.
    """
    if df_diario.empty or "dia" not in df_diario.columns or "consumo_kwh" not in df_diario.columns:
        return ""

    df_sorted = df_diario.sort_values("dia").reset_index(drop=True)
    dias = [str(d) for d in df_sorted["dia"]]
    consumos = [float(c) for c in df_sorted["consumo_kwh"]]
    completos = [bool(c) for c in df_sorted.get("dia_completo", [True] * len(df_sorted))]
    participacoes = df_sorted.get("participacao_percentual", [None] * len(df_sorted))

    # Formatar rótulos do eixo X (ex: '01/08\nSáb')
    rotulos_x = []
    for d_str in dias:
        try:
            dt = pd.to_datetime(d_str)
            rotulos_x.append(f"{dt.strftime('%d/%m')}\n{DIAS_SEMANA_PT.get(dt.weekday(), '')}")
        except Exception:
            rotulos_x.append(d_str)

    fig, ax = plt.subplots(figsize=(11, 4.2), dpi=140)

    cores = []
    hachuras = []
    for d_str, comp in zip(dias, completos):
        if d_str == dia_maior_consumo:
            cores.append("#dc2626")  # Destaque vermelho
            hachuras.append("")
        elif comp:
            cores.append("#2563eb")  # Azul sólido
            hachuras.append("")
        else:
            cores.append("#f59e0b")  # Âmbar para parcial
            hachuras.append("//")

    barras = ax.bar(
        range(len(dias)),
        consumos,
        color=cores,
        hatch=hachuras,
        edgecolor="#1e293b",
        linewidth=0.8,
        width=0.55,
        zorder=2,
    )

    # Anotações de valor sobre as barras
    y_max = max(consumos) if consumos else 10.0
    for i, (bar, c_val, p_val) in enumerate(zip(barras, consumos, participacoes)):
        txt = formatar_numero_br(c_val, 1) + " kWh"
        if p_val is not None and not pd.isna(p_val) and float(p_val) > 0:
            txt += f"\n({formatar_numero_br(float(p_val), 1)}%)"
        ax.annotate(
            txt,
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=7.5,
            color="#0f172a",
            fontweight="bold",
        )

    ax.set_xticks(range(len(dias)))
    ax.set_xticklabels(rotulos_x, fontsize=8, color="#334155")
    ax.set_ylabel("Energia Elétrica Ativa (kWh)", fontsize=9, fontweight="bold", color="#1e293b", labelpad=8)
    ax.set_xlabel("Data Civil", fontsize=9, fontweight="bold", color="#1e293b", labelpad=8)
    ax.set_ylim(bottom=0, top=max(10.0, y_max * 1.25))
    ax.grid(True, axis="y", linestyle=":", alpha=0.6, color="#cbd5e1", zorder=1)
    ax.tick_params(axis="y", labelsize=8, colors="#334155")

    # Legenda customizada
    from matplotlib.patches import Patch
    legenda_itens = [
        Patch(facecolor="#2563eb", edgecolor="#1e293b", label="Dia Completo (24h)"),
        Patch(facecolor="#f59e0b", edgecolor="#1e293b", hatch="//", label="Dia Parcial (< 24h)"),
        Patch(facecolor="#dc2626", edgecolor="#1e293b", label="Maior Consumo Registrado"),
    ]
    ax.legend(
        handles=legenda_itens,
        loc="upper left",
        bbox_to_anchor=(0.0, 1.15),
        ncol=3,
        frameon=True,
        facecolor="#f8fafc",
        edgecolor="#cbd5e1",
        fontsize=8.5,
    )

    return _fig_para_base64(fig)


def gerar_mapa_calor_base64(
    df_historico: pd.DataFrame,
    intervalo_horas: float,
) -> str:
    """Gera matriz visual (Data × Horário do Intervalo) e retorna imagem Base64.

    Rigor Técnico e Visual:
    - Linhas = Datas civis; Colunas = Intervalos de medição ao longo das 24 horas.
    - Intervalos ausentes (lacunas) recebem cinza neutro (#e2e8f0) com legenda explícita.
    - Potência zero válida (0,00 kW) recebe cor clara da escala (#ffffcc), visualmente distinta da ausência.
    - Não aplica qualquer interpolação, suavização ou preenchimento artificial.
    """
    if df_historico.empty or "data_hora" not in df_historico.columns or "potencia_kw" not in df_historico.columns:
        return ""

    df_temp = df_historico.copy()
    df_temp["data_hora"] = pd.to_datetime(df_temp["data_hora"])
    df_temp = df_temp.sort_values("data_hora").reset_index(drop=True)

    df_temp["dia"] = df_temp["data_hora"].dt.strftime("%Y-%m-%d")
    df_temp["hora"] = df_temp["data_hora"].dt.strftime("%H:%M")

    # Grade completa de horários possíveis em um dia
    minutos_passo = int(round(intervalo_horas * 60))
    col_times = [
        f"{h:02d}:{m:02d}"
        for h in range(24)
        for m in range(0, 60, minutos_passo)
    ]

    t_min = df_temp["data_hora"].iloc[0].floor("D")
    t_max = df_temp["data_hora"].iloc[-1].floor("D")
    datas_todas = [d.strftime("%Y-%m-%d") for d in pd.date_range(t_min, t_max, freq="1D")]

    # Criar pivot table com reindexação completa de linhas e colunas
    pivot = df_temp.pivot_table(
        index="dia",
        columns="hora",
        values="potencia_kw",
        aggfunc="first",
    )
    pivot = pivot.reindex(index=datas_todas, columns=col_times)

    valores = pivot.to_numpy(dtype=float)
    valores_mascarados = np.ma.masked_invalid(valores)

    # Configuração de altura adaptativa da figura
    n_dias = len(datas_todas)
    fig_height = max(3.5, min(14.0, n_dias * 0.45 + 1.8))
    fig, ax = plt.subplots(figsize=(11.5, fig_height), dpi=140)

    cmap = matplotlib.colormaps["YlOrRd"].copy()
    if hasattr(cmap, "with_extremes"):
        cmap = cmap.with_extremes(bad="#e2e8f0")
    else:
        cmap.set_bad(color="#e2e8f0")

    p_max_val = np.nanmax(valores) if not np.all(np.isnan(valores)) else 10.0
    im = ax.imshow(
        valores_mascarados,
        cmap=cmap,
        aspect="auto",
        vmin=0.0,
        vmax=max(5.0, p_max_val),
        origin="upper",
        interpolation="none",
    )

    # Barra de cores
    cbar = fig.colorbar(im, ax=ax, orientation="vertical", pad=0.02, shrink=0.85)
    cbar.set_label("Potência Ativa Média (kW)", fontsize=8.5, fontweight="bold", color="#1e293b")
    cbar.ax.tick_params(labelsize=8, colors="#334155")

    # Rótulos Y (Datas)
    rotulos_y = []
    for d_str in datas_todas:
        try:
            dt = pd.to_datetime(d_str)
            rotulos_y.append(f"{dt.strftime('%d/%m')} ({DIAS_SEMANA_PT.get(dt.weekday(), '')})")
        except Exception:
            rotulos_y.append(d_str)

    ax.set_yticks(range(n_dias))
    ax.set_yticklabels(rotulos_y, fontsize=8, color="#334155")

    # Rótulos X (Horários) - Reduzir densidade quando passo < 1h
    if intervalo_horas == 1.0:
        passo_label = 2
    elif intervalo_horas == 0.5:
        passo_label = 4
    else:
        passo_label = 8

    indices_x = list(range(0, len(col_times), passo_label))
    rotulos_x = [col_times[i] for i in indices_x]
    ax.set_xticks(indices_x)
    ax.set_xticklabels(rotulos_x, fontsize=7.5, color="#334155", rotation=0)

    ax.set_ylabel("Data Civil", fontsize=9, fontweight="bold", color="#1e293b", labelpad=8)
    ax.set_xlabel(f"Horário de Início do Intervalo ({minutos_passo} min)", fontsize=9, fontweight="bold", color="#1e293b", labelpad=8)

    # Legenda descritiva de dados ausentes vs potência zero
    from matplotlib.patches import Patch
    legenda_itens = [
        Patch(facecolor="#e2e8f0", edgecolor="#94a3b8", label="Intervalo ausente (sem registro de medição)"),
        Patch(facecolor="#ffffcc", edgecolor="#cbd5e1", label="Potência zero válida (0,00 kW)"),
    ]
    ax.legend(
        handles=legenda_itens,
        loc="upper left",
        bbox_to_anchor=(0.0, 1.15),
        ncol=2,
        frameon=True,
        facecolor="#f8fafc",
        edgecolor="#cbd5e1",
        fontsize=8.5,
    )

    return _fig_para_base64(fig)


def construir_conteudo_html(
    indicadores: Union[IndicadoresCompletosDict, Dict[str, Any]],
    df_diario: pd.DataFrame,
    df_historico: pd.DataFrame,
    estatisticas_lote: Optional[Dict[str, int]] = None,
    avisos_lote: Optional[List[str]] = None,
    avisos_historico: Optional[List[str]] = None,
    intervalo_horas: float = 1.0,
    origem_dados: Optional[str] = None,
) -> str:
    """Monta o documento HTML completo e estilizado com todos os indicadores e visualizações.

    Seções estruturadas (A até H):
    A. Cabeçalho (identificação, período, intervalo, geração, escopo e origem dos dados);
    B. Indicadores principais (6 cards formatados);
    C. Curva de carga (potência ativa média no tempo com quebra em lacunas);
    D. Consumo diário (barras cronológicas com segregação de dias parciais);
    E. Mapa de calor (Dia × Horário com tratamento estrito de ausências);
    F. Qualidade dos dados (balanço lote CSV vs histórico SQLite e alertas);
    G. Síntese executiva e limitações regulatórias;
    H. Tabela diária consolidada com números no padrão brasileiro.
    """
    total_med = int(indicadores.get("total_medicoes", 0))
    p_inicio = html.escape(str(indicadores.get("periodo_inicio") or "N/D"))
    p_fim = html.escape(str(indicadores.get("periodo_fim") or "N/D"))

    # Origem dos dados com tratamento honesto
    if origem_dados and str(origem_dados).strip().lower() in ("simulados", "simulado"):
        badge_origem = '<span class="badge badge-simulado">Dados Simulados (Didáticos)</span>'
    elif origem_dados and str(origem_dados).strip().lower() in ("reais", "real"):
        badge_origem = '<span class="badge badge-real">Dados Reais de Medição</span>'
    else:
        badge_origem = '<span class="badge badge-neutro">Origem não informada</span>'

    # Carimbo de data/hora de geração com fuso local
    now = datetime.now()
    fuso_str = time.tzname[time.daylight] if time.daylight and len(time.tzname) > 1 else time.tzname[0]
    data_geracao_fmt = f"{now.strftime('%d/%m/%Y às %H:%M:%S')} ({fuso_str})"

    minutos_passo = int(round(intervalo_horas * 60))
    desc_resolucao = f"1,0 h (60 min)" if intervalo_horas == 1.0 else f"{intervalo_horas} h ({minutos_passo} min)"

    # Indicadores numéricos
    pot_media = indicadores.get("potencia_media_kw", 0.0)
    pot_media_str = formatar_numero_br(pot_media, 2) if pot_media is not None else "Não aplicável"

    demanda_max = indicadores.get("demanda_maxima_kw", 0.0)
    demanda_max_str = formatar_numero_br(demanda_max, 2) if demanda_max is not None and demanda_max > 0 else "Não aplicável"
    horario_max = indicadores.get("horario_demanda_maxima")
    horario_max_str = html.escape(str(horario_max)) if horario_max else "N/D"

    rotulo_card_pico = (
        "Maior Potência Média Horária (Pico)"
        if intervalo_horas == 1.0
        else f"Maior Potência Média (Pico, {minutos_passo} min)"
    )

    energia_tot = indicadores.get("consumo_total_kwh", 0.0)
    energia_tot_str = formatar_numero_br(energia_tot, 2)

    tarifa = indicadores.get("tarifa_kwh", 0.0)
    tarifa_str = formatar_numero_br(tarifa, 2)

    custo_tot = indicadores.get("custo_estimado_reais", 0.0)
    custo_tot_str = formatar_numero_br(custo_tot, 2)

    fc_pct = indicadores.get("fator_carga_percentual")
    fc_str = f"{formatar_numero_br(fc_pct, 2)}%" if fc_pct is not None else "Não aplicável"

    cobertura = indicadores.get("cobertura", {})
    pct_cob = cobertura.get("percentual_cobertura")
    cob_str = f"{formatar_numero_br(pct_cob, 1)}%" if pct_cob is not None else "Não aplicável"
    h_medidas = cobertura.get("horas_medidas", total_med)
    h_esperadas = cobertura.get("horas_esperadas", total_med)
    h_ausentes = cobertura.get("horas_ausentes", 0)

    # Geração dos gráficos Base64
    img_curva = gerar_curva_de_carga_base64(
        df_historico=df_historico,
        intervalo_horas=intervalo_horas,
        demanda_maxima=demanda_max or 0.0,
        horario_max=horario_max,
        potencia_media=pot_media or 0.0,
    )

    dia_max = indicadores.get("dia_maior_consumo")
    img_consumo = gerar_grafico_consumo_diario_base64(
        df_diario=df_diario,
        dia_maior_consumo=dia_max,
    )

    img_calor = gerar_mapa_calor_base64(
        df_historico=df_historico,
        intervalo_horas=intervalo_horas,
    )

    # Síntese Executiva
    tem_lacunas = bool(avisos_historico or h_ausentes > 0)
    sintese_txt = gerar_sintese_executiva(indicadores, df_diario, tem_lacunas=tem_lacunas)
    sintese_html = "".join(f"<p>{html.escape(p)}</p>" for p in sintese_txt.split("\n\n") if p.strip())

    # Qualidade dos dados - Estatísticas do Lote
    if estatisticas_lote:
        lote_lidos = str(estatisticas_lote.get("total_lidos", 0))
        lote_validos = str(estatisticas_lote.get("registros_validos", 0))
        lote_descartados = str(estatisticas_lote.get("linhas_descartadas", 0))
        lote_novos = str(estatisticas_lote.get("novos_inseridos", 0))
    else:
        lote_lidos = lote_validos = lote_descartados = lote_novos = "N/D"

    # Qualidade dos dados - Dias no Histórico
    dias_completos_count = int((df_diario["dia_completo"] == True).sum()) if not df_diario.empty and "dia_completo" in df_diario.columns else 0
    dias_parciais_count = int((df_diario["dia_completo"] == False).sum()) if not df_diario.empty and "dia_completo" in df_diario.columns else 0

    # Avisos formatados
    avisos_totais = []
    if avisos_lote:
        avisos_totais.extend([f"<strong>Importação CSV:</strong> {html.escape(a)}" for a in avisos_lote[:4]])
    if avisos_historico:
        avisos_totais.extend([f"<strong>Histórico SQLite:</strong> {html.escape(a)}" for a in avisos_historico[:4]])

    if avisos_totais:
        avisos_html = "<ul class='lista-avisos'>" + "".join(f"<li>{item}</li>" for item in avisos_totais) + "</ul>"
    else:
        avisos_html = "<p class='texto-sucesso'>Nenhuma inconsistência ou lacuna temporal detectada na série analisada.</p>"

    # Tabela diária HTML
    linhas_tabela = []
    if not df_diario.empty:
        for _, row in df_diario.iterrows():
            d_val = html.escape(str(row.get("dia", "")))
            meds_val = str(row.get("total_medicoes", ""))
            comp_val = bool(row.get("dia_completo", True))
            status_tag = '<span class="tag tag-ok">Completo (24h)</span>' if comp_val else f'<span class="tag tag-parcial">{meds_val} meds (Parcial)</span>'
            pm_val = formatar_numero_br(float(row.get("potencia_media_kw", 0.0)), 2)
            dm_val = formatar_numero_br(float(row.get("demanda_maxima_kw", 0.0)), 2)
            ck_val = formatar_numero_br(float(row.get("consumo_kwh", 0.0)), 2)
            part_val = row.get("participacao_percentual")
            part_str = f"{formatar_numero_br(float(part_val), 2)}%" if part_val is not None and not pd.isna(part_val) else "N/A"
            custo_dia_str = formatar_numero_br(float(row.get("consumo_kwh", 0.0)) * tarifa, 2)

            linhas_tabela.append(
                f"<tr>"
                f"<td><strong>{d_val}</strong></td>"
                f"<td>{meds_val}</td>"
                f"<td>{status_tag}</td>"
                f"<td>{pm_val} kW</td>"
                f"<td>{dm_val} kW</td>"
                f"<td>{ck_val} kWh</td>"
                f"<td>{part_str}</td>"
                f"<td>R$ {custo_dia_str}</td>"
                f"</tr>"
            )
    tabela_diaria_linhas = "\n".join(linhas_tabela)

    unidade_passos = "horas esperadas" if intervalo_horas == 1.0 else "intervalos esperados"

    html_template = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PowerMonitor — Relatório de Consumo e Demanda</title>
    <style>
        /* Estilos autocontidos: Tema Claro, Tipografia de Sistema e Alto Contraste */
        *, *::before, *::after {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f8fafc;
            color: #0f172a;
            line-height: 1.55;
            font-size: 14.5px;
            padding: 24px 16px;
        }}

        .container {{
            max-width: 1180px;
            margin: 0 auto;
        }}

        /* Cabeçalho */
        header.header-relatorio {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
        }}

        .header-top {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 16px;
        }}

        h1.logo {{
            font-size: 24px;
            font-weight: 800;
            letter-spacing: -0.5px;
            color: #1e3a8a;
        }}

        p.subtitulo {{
            font-size: 14px;
            color: #475569;
            font-weight: 500;
        }}

        .metadados-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 12px;
            padding-top: 14px;
            border-top: 1px solid #f1f5f9;
            font-size: 13px;
        }}

        .meta-item strong {{
            color: #334155;
            display: block;
            margin-bottom: 2px;
        }}

        .meta-item span {{
            color: #0f172a;
        }}

        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge-simulado {{ background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }}
        .badge-real {{ background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; }}
        .badge-neutro {{ background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }}

        /* Seções e Títulos */
        section.secao-relatorio {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
        }}

        h2.secao-titulo {{
            font-size: 17px;
            font-weight: 700;
            color: #1e293b;
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 2px solid #e2e8f0;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        /* Cards de Indicadores */
        .cards-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
            margin-bottom: 8px;
        }}

        .card {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 16px;
            position: relative;
        }}

        .card-rotulo {{
            font-size: 12.5px;
            font-weight: 600;
            color: #475569;
            text-transform: uppercase;
            letter-spacing: 0.3px;
            margin-bottom: 6px;
        }}

        .card-valor {{
            font-size: 22px;
            font-weight: 800;
            color: #0f172a;
            margin-bottom: 4px;
        }}

        .card-destaque {{
            font-size: 12px;
            color: #dc2626;
            font-weight: 600;
        }}

        .card-nota {{
            font-size: 11.5px;
            color: #64748b;
            margin-top: 6px;
            line-height: 1.4;
        }}

        /* Gráficos */
        figure.grafico-wrapper {{
            margin: 0 auto;
            text-align: center;
        }}

        figure.grafico-wrapper img {{
            max-width: 100%;
            height: auto;
            border-radius: 6px;
            border: 1px solid #f1f5f9;
        }}

        figcaption.grafico-legenda {{
            font-size: 12.5px;
            color: #475569;
            margin-top: 12px;
            text-align: left;
            background: #f8fafc;
            padding: 10px 14px;
            border-radius: 6px;
            border-left: 3px solid #2563eb;
        }}

        /* Qualidade dos Dados */
        .qualidade-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
            margin-bottom: 16px;
        }}

        .painel-qualidade {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 14px 18px;
        }}

        .painel-qualidade h3 {{
            font-size: 13.5px;
            color: #1e293b;
            margin-bottom: 10px;
            font-weight: 700;
        }}

        .linha-estatistica {{
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            font-size: 13px;
            border-bottom: 1px dashed #e2e8f0;
        }}
        .linha-estatistica:last-child {{
            border-bottom: none;
        }}

        .lista-avisos {{
            list-style: none;
            margin-top: 8px;
        }}
        .lista-avisos li {{
            background: #fffbeb;
            border-left: 3px solid #f59e0b;
            color: #92400e;
            padding: 8px 12px;
            font-size: 12.5px;
            margin-bottom: 8px;
            border-radius: 0 4px 4px 0;
        }}

        .texto-sucesso {{
            color: #047857;
            font-size: 13px;
            font-weight: 600;
        }}

        /* Síntese e Aviso Regulatório */
        .sintese-texto p {{
            margin-bottom: 12px;
            color: #334155;
            font-size: 14px;
            text-align: justify;
        }}

        .aviso-regulatorio {{
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            border-left: 4px solid #2563eb;
            border-radius: 6px;
            padding: 14px 18px;
            margin-top: 16px;
            font-size: 13px;
            color: #1e40af;
        }}
        .aviso-regulatorio strong {{
            display: block;
            margin-bottom: 4px;
            color: #1e3a8a;
        }}

        /* Tabela Diária Responsiva */
        .table-responsive {{
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            margin-top: 8px;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
        }}

        table.tabela-diaria {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
            min-width: 680px;
        }}

        table.tabela-diaria th {{
            background: #f1f5f9;
            color: #334155;
            padding: 10px 14px;
            font-weight: 700;
            border-bottom: 2px solid #cbd5e1;
            white-space: nowrap;
        }}

        table.tabela-diaria td {{
            padding: 10px 14px;
            border-bottom: 1px solid #e2e8f0;
            color: #1e293b;
        }}

        table.tabela-diaria tr:last-child td {{
            border-bottom: none;
        }}

        table.tabela-diaria tr:hover {{
            background: #f8fafc;
        }}

        .tag {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}
        .tag-ok {{ background: #dcfce7; color: #15803d; }}
        .tag-parcial {{ background: #fef3c7; color: #b45309; }}

        /* Rodapé */
        footer.footer-relatorio {{
            text-align: center;
            font-size: 12px;
            color: #64748b;
            margin-top: 32px;
            padding: 16px;
        }}

        /* Estilos de Impressão */
        @media print {{
            body {{
                background: #ffffff;
                padding: 0;
                font-size: 11pt;
            }}
            .container {{
                max-width: 100%;
            }}
            header.header-relatorio,
            section.secao-relatorio {{
                border: 1px solid #cbd5e1;
                box-shadow: none;
                page-break-inside: avoid;
                margin-bottom: 18px;
                padding: 16px;
            }}
            .card {{
                border: 1px solid #cbd5e1;
            }}
            table.tabela-diaria th, table.tabela-diaria td {{
                padding: 6px 10px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">

        <!-- SEÇÃO A: Cabeçalho -->
        <header class="header-relatorio">
            <div class="header-top">
                <div>
                    <h1 class="logo">PowerMonitor</h1>
                    <p class="subtitulo">Análise de consumo elétrico e qualidade das medições &bull; Desenvolvido por Eng. Ely Barros</p>
                </div>
                <div>
                    {badge_origem}
                </div>
            </div>

            <div class="metadados-grid">
                <div class="meta-item">
                    <strong>Período Analisado:</strong>
                    <span>{p_inicio} a {p_fim}</span>
                    <div style="font-size: 11px; color: #64748b;">(do início da 1ª medição ao fim do último intervalo)</div>
                </div>
                <div class="meta-item">
                    <strong>Resolução Amostral:</strong>
                    <span>{desc_resolucao}</span>
                </div>
                <div class="meta-item">
                    <strong>Data de Geração:</strong>
                    <span>{data_geracao_fmt}</span>
                </div>
                <div class="meta-item">
                    <strong>Escopo dos Dados:</strong>
                    <span>Histórico no SQLite ({total_med} medições)</span>
                </div>
            </div>
        </header>

        <main>
            <!-- SEÇÃO B: Indicadores Principais -->
            <section class="secao-relatorio">
                <h2 class="secao-titulo">1. Indicadores Principais de Carregamento</h2>
                <div class="cards-grid">
                    <div class="card">
                        <div class="card-rotulo">Energia Registrada</div>
                        <div class="card-valor">{energia_tot_str} <span style="font-size: 15px; font-weight: 500;">kWh</span></div>
                        <div class="card-nota">Integral da potência ativa no tempo (&Sigma; P &times; &Delta;t).</div>
                    </div>

                    <div class="card">
                        <div class="card-rotulo">Potência Média</div>
                        <div class="card-valor">{pot_media_str} <span style="font-size: 15px; font-weight: 500;">kW</span></div>
                        <div class="card-nota">Demanda média aritmética solicitada pela instalação.</div>
                    </div>

                    <div class="card">
                        <div class="card-rotulo">{rotulo_card_pico}</div>
                        <div class="card-valor">{demanda_max_str} <span style="font-size: 15px; font-weight: 500;">kW</span></div>
                        <div class="card-destaque">Registrado em: {horario_max_str}</div>
                        <div class="card-nota">Maior solicitação média no intervalo amostral.</div>
                    </div>

                    <div class="card">
                        <div class="card-rotulo">Fator de Carga</div>
                        <div class="card-valor">{fc_str}</div>
                        <div class="card-nota">Razão potência média / pico. Indica uniformidade da carga, <strong>não</strong> eficiência dos equipamentos.</div>
                    </div>

                    <div class="card">
                        <div class="card-rotulo">Cobertura Temporal</div>
                        <div class="card-valor">{cob_str}</div>
                        <div class="card-nota">{h_medidas} de {h_esperadas} {unidade_passos} monitorados. Refere-se aos limites da série, não a dias civis cheios.</div>
                    </div>

                    <div class="card">
                        <div class="card-rotulo">Simulação de Custo</div>
                        <div class="card-valor"><span style="font-size: 16px; font-weight: 600;">R$</span> {custo_tot_str}</div>
                        <div class="card-nota">Tarifa linear de R$ {tarifa_str}/kWh. Estimativa analítica simplificada; <strong>não constitui fatura</strong>.</div>
                    </div>
                </div>
            </section>

            <!-- SEÇÃO C: Curva de Carga -->
            <section class="secao-relatorio">
                <h2 class="secao-titulo">2. Curva de Carga Temporal</h2>
                <figure class="grafico-wrapper">
                    <img src="{img_curva}" alt="Curva de Carga Temporal" />
                    <figcaption class="grafico-legenda">
                        <strong>Interpretação Física:</strong> A curva apresenta a potência ativa média registrada em cada intervalo amostral (&Delta;t). A linha verde tracejada indica o patamar médio ({pot_media_str} kW) e o ponto vermelho destaca o pico de demanda ({demanda_max_str} kW em {horario_max_str}). Em conformidade metrológica, a linha é <strong>interrompida em intervalos ausentes</strong> para não induzir presunção de medições inexistentes.
                    </figcaption>
                </figure>
            </section>

            <!-- SEÇÃO D: Consumo Diário -->
            <section class="secao-relatorio">
                <h2 class="secao-titulo">3. Consumo Diário de Energia</h2>
                <figure class="grafico-wrapper">
                    <img src="{img_consumo}" alt="Consumo Diário de Energia" />
                    <figcaption class="grafico-legenda">
                        <strong>Dinâmica Diária:</strong> Barras em azul representam dias com cobertura integral (24h OK). Barras hachuradas em âmbar representam dias parciais, cujo consumo abrange estritamente as horas com dados válidos e não deve ser comparado diretamente a dias completos. A barra vermelha destaca o dia de maior consumo acumulado.
                    </figcaption>
                </figure>
            </section>

            <!-- SEÇÃO E: Mapa de Calor (Dia x Horário) -->
            <section class="secao-relatorio">
                <h2 class="secao-titulo">4. Mapa de Calor Operacional (Dia &times; Horário)</h2>
                <figure class="grafico-wrapper">
                    <img src="{img_calor}" alt="Mapa de Calor Dia por Horário" />
                    <figcaption class="grafico-legenda">
                        <strong>Matriz Operacional:</strong> Permite identificar visualmente a modulação de turnos, simultaneidade de cargas e horários de ponta. Células em <strong>cinza neutro</strong> indicam estritamente ausência de medição (lacunas), enquanto valores de <strong>potência zero válida (0,00 kW)</strong> são diferenciados na escala clara de cor. Nenhuma interpolação matemática é aplicada.
                    </figcaption>
                </figure>
            </section>

            <!-- SEÇÃO F: Qualidade dos Dados -->
            <section class="secao-relatorio">
                <h2 class="secao-titulo">5. Auditoria de Qualidade e Integridade dos Dados</h2>
                <div class="qualidade-grid">
                    <div class="painel-qualidade">
                        <h3>Lote da Importação Atual (CSV)</h3>
                        <div class="linha-estatistica"><span>Linhas lidas no arquivo:</span><strong>{lote_lidos}</strong></div>
                        <div class="linha-estatistica"><span>Medições válidas no lote:</span><strong>{lote_validos}</strong></div>
                        <div class="linha-estatistica"><span>Linhas descartadas (ruído/erro):</span><strong>{lote_descartados}</strong></div>
                        <div class="linha-estatistica"><span>Novas medições inseridas no SQLite:</span><strong>{lote_novos}</strong></div>
                    </div>

                    <div class="painel-qualidade">
                        <h3>Histórico Consolidado (Banco SQLite)</h3>
                        <div class="linha-estatistica"><span>Total de medições no banco:</span><strong>{total_med}</strong></div>
                        <div class="linha-estatistica"><span>Intervalos temporais esperados:</span><strong>{h_esperadas}</strong></div>
                        <div class="linha-estatistica"><span>Intervalos medidos / ausentes:</span><strong>{h_medidas} / {h_ausentes}</strong></div>
                        <div class="linha-estatistica"><span>Dias completos / parciais:</span><strong>{dias_completos_count} / {dias_parciais_count}</strong></div>
                    </div>
                </div>

                <div>
                    <h3 style="font-size: 13px; color: #334155; margin-bottom: 6px;">Observações e Alertas de Validação:</h3>
                    {avisos_html}
                </div>
            </section>

            <!-- SEÇÃO G: Síntese e Limites -->
            <section class="secao-relatorio">
                <h2 class="secao-titulo">6. Síntese dos Resultados e Recomendações Técnicas</h2>
                <div class="sintese-texto">
                    {sintese_html}
                </div>

                <div class="aviso-regulatorio">
                    <strong>Nota Regulatória e Metrológica:</strong>
                    O relatório apresenta análise educacional de medições elétricas. A estimativa de custo é simplificada e não substitui cálculos de faturamento ou verificações de conformidade regulatória (REN ANEEL nº 1.000/2021). Não contempla demanda faturável em R$/kW, custo de disponibilidade, faixas de Tarifa Branca, adicionais de bandeiras tarifárias ou tributos.
                </div>
            </section>

            <!-- SEÇÃO H: Tabela Diária -->
            <section class="secao-relatorio">
                <h2 class="secao-titulo">7. Tabela Diária Consolidada</h2>
                <div class="table-responsive">
                    <table class="tabela-diaria">
                        <thead>
                            <tr>
                                <th>Data Civil</th>
                                <th>Medições</th>
                                <th>Status</th>
                                <th>Potência Média</th>
                                <th>Pico de Demanda</th>
                                <th>Consumo Diário</th>
                                <th>Participação</th>
                                <th>Custo Estimado</th>
                            </tr>
                        </thead>
                        <tbody>
                            {tabela_diaria_linhas}
                        </tbody>
                    </table>
                </div>
            </section>
        </main>

        <footer class="footer-relatorio">
            <p><strong>PowerMonitor v1.0</strong> — Desenvolvido por Eng. Ely Barros</p>
            <p style="font-size: 11px; margin-top: 4px; color: #94a3b8;">Relatório gerado localmente em arquivo único estático (sem dependências externas).</p>
        </footer>

    </div>
</body>
</html>
"""
    return html_template


def salvar_relatorio_html(
    conteudo_html: str,
    output_path: Union[str, Path],
) -> Path:
    """Salva o conteúdo HTML de forma atômica no caminho de destino.

    Garante criação defensiva de diretórios pais e escrita atômica via arquivo temporário,
    evitando que um arquivo parcial ou corrompido seja deixado em caso de erro de I/O.
    """
    path = Path(output_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(conteudo_html, encoding="utf-8")
        temp_path.replace(path)
        return path
    except Exception as e:
        raise RuntimeError(f"Erro ao salvar relatório HTML em '{path}': {e}") from e
