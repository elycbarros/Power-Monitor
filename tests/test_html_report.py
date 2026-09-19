"""Testes unitários e de integração para o relatório visual em HTML (src/html_report.py).

Garante:
- Geração correta de imagens PNG embutidas em Base64 (curva de carga, consumo diário e mapa de calor);
- Presença de todas as seções A até H conforme especificação do projeto;
- Ausência total de recursos e scripts externos (segurança e funcionamento 100% offline);
- Sanitização de strings dinâmicas (prevenção contra injeção de HTML/XSS);
- Tratamento robusto de casos de borda (lacunas temporais, potência zero, medição única, dias parciais);
- Integração de ponta a ponta via CLI e função orquestradora do pipeline (`main.py`).
"""

import math
from pathlib import Path
import re
import pytest
import pandas as pd
import numpy as np

import main
import config
from src.analysis import gerar_indicadores_completos
from src.html_report import (
    gerar_curva_de_carga_base64,
    gerar_grafico_consumo_diario_base64,
    gerar_mapa_calor_base64,
    construir_conteudo_html,
    salvar_relatorio_html,
)


@pytest.fixture
def df_exemplo_7dias():
    """Gera DataFrame com 7 dias completos (168 horas) com consumo típico."""
    ts = pd.date_range("2026-08-01 00:00", "2026-08-07 23:00", freq="1h")
    # Padrão senoidal suave com pico conhecido
    potencias = [10.0 + 5.0 * math.sin(i / 12.0 * math.pi) for i in range(len(ts))]
    potencias[42] = 28.5  # Pico pontual
    return pd.DataFrame({"data_hora": ts, "potencia_kw": potencias})


def test_geracao_graficos_base64_validos(df_exemplo_7dias):
    """Verifica se os geradores de gráficos produzem Data URIs Base64 válidas e tratam DataFrames vazios."""
    indicadores = gerar_indicadores_completos(df_exemplo_7dias, tarifa_kwh=0.75, intervalo_horas=1.0)
    df_diario = indicadores["df_diario"]

    # 1. Curva de Carga
    b64_curva = gerar_curva_de_carga_base64(
        df_historico=df_exemplo_7dias,
        intervalo_horas=1.0,
        demanda_maxima=indicadores["demanda_maxima_kw"],
        horario_max=indicadores["horario_demanda_maxima"],
        potencia_media=indicadores["potencia_media_kw"],
    )
    assert b64_curva.startswith("data:image/png;base64,")
    assert len(b64_curva) > 500

    # 2. Consumo Diário
    b64_consumo = gerar_grafico_consumo_diario_base64(
        df_diario=df_diario,
        dia_maior_consumo=indicadores["dia_maior_consumo"],
    )
    assert b64_consumo.startswith("data:image/png;base64,")
    assert len(b64_consumo) > 500

    # 3. Mapa de Calor
    b64_calor = gerar_mapa_calor_base64(
        df_historico=df_exemplo_7dias,
        intervalo_horas=1.0,
    )
    assert b64_calor.startswith("data:image/png;base64,")
    assert len(b64_calor) > 500

    # 4. Caso vazio retorna string vazia
    df_vazio = pd.DataFrame(columns=["data_hora", "potencia_kw"])
    assert gerar_curva_de_carga_base64(df_vazio, 1.0, 0.0, None, 0.0) == ""
    assert gerar_grafico_consumo_diario_base64(pd.DataFrame(), None) == ""
    assert gerar_mapa_calor_base64(df_vazio, 1.0) == ""


def test_relatorio_html_estrutura_e_secoes_obrigatorias(df_exemplo_7dias):
    """Garante a presença de todas as seções especificadas (A até H) e das notas regulatórias."""
    indicadores = gerar_indicadores_completos(df_exemplo_7dias, tarifa_kwh=0.75, intervalo_horas=1.0)
    df_diario = indicadores["df_diario"]

    html_out = construir_conteudo_html(
        indicadores=indicadores,
        df_diario=df_diario,
        df_historico=df_exemplo_7dias,
        estatisticas_lote={"total_lidos": 168, "registros_validos": 168, "linhas_descartadas": 0, "novos_inseridos": 168},
        avisos_lote=None,
        avisos_historico=None,
        intervalo_horas=1.0,
        origem_dados="simulados",
    )

    # A. Cabeçalho
    assert "PowerMonitor" in html_out
    assert "Análise de consumo elétrico e qualidade das medições" in html_out
    assert "Dados Simulados (Didáticos)" in html_out
    assert "Histórico no SQLite (168 medições)" in html_out

    # B. Indicadores Principais
    assert "Energia Registrada" in html_out
    assert "Potência Média" in html_out
    assert "Maior Potência Média Horária (Pico)" in html_out
    assert "Fator de Carga" in html_out
    assert "Cobertura Temporal" in html_out
    assert "Simulação de Custo" in html_out

    # C, D, E. Imagens Base64 presentes
    assert html_out.count("data:image/png;base64,") == 3

    # F. Qualidade dos Dados
    assert "Auditoria de Qualidade e Integridade dos Dados" in html_out
    assert "Lote da Importação Atual (CSV)" in html_out
    assert "Histórico Consolidado (Banco SQLite)" in html_out

    # G. Síntese e Aviso Regulatório Obrigatório
    assert "Síntese dos Resultados e Recomendações Técnicas" in html_out
    assert "O relatório apresenta análise educacional de medições elétricas" in html_out
    assert "não substitui cálculos de faturamento ou verificações de conformidade regulatória" in html_out

    # H. Tabela Diária
    assert "Tabela Diária Consolidada" in html_out
    assert "class=\"tabela-diaria\"" in html_out
    assert "Completo (24h)" in html_out


def test_relatorio_html_ausencia_recursos_externos(df_exemplo_7dias):
    """Comprova que o relatório é 100% offline e não contém referências a CDNs, links externos ou scripts remotos."""
    indicadores = gerar_indicadores_completos(df_exemplo_7dias, tarifa_kwh=0.75, intervalo_horas=1.0)
    html_out = construir_conteudo_html(
        indicadores=indicadores,
        df_diario=indicadores["df_diario"],
        df_historico=df_exemplo_7dias,
    )

    # Remover data URIs base64 antes de verificar texto do markup
    html_markup = re.sub(r'src="data:image/[^"]+"', '', html_out)

    # Não deve ter chamadas a serviços externos
    assert "http://" not in html_markup
    assert "https://" not in html_markup
    assert "<script" not in html_markup
    assert "<link" not in html_markup
    assert "googleapis" not in html_markup
    assert "cdn" not in html_markup


def test_relatorio_html_escape_xss(df_exemplo_7dias):
    """Verifica se variáveis dinâmicas com possíveis tags HTML maliciosas são escapadas com html.escape."""
    indicadores = gerar_indicadores_completos(df_exemplo_7dias, tarifa_kwh=0.75, intervalo_horas=1.0)
    html_malicioso = "<script>alert('xss')</script>"

    html_out = construir_conteudo_html(
        indicadores=indicadores,
        df_diario=indicadores["df_diario"],
        df_historico=df_exemplo_7dias,
        avisos_lote=[html_malicioso],
        avisos_historico=[html_malicioso],
    )

    assert html_malicioso not in html_out
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html_out


def test_relatorio_html_casos_borda():
    """Valida comportamento defensivo com medição única, consumo zero, dias parciais e lacunas."""
    # 1. Medição única
    df_uma = pd.DataFrame({"data_hora": ["2026-08-01 08:00"], "potencia_kw": [15.0]})
    ind_uma = gerar_indicadores_completos(df_uma, tarifa_kwh=0.75, intervalo_horas=1.0)

    html_uma = construir_conteudo_html(
        indicadores=ind_uma,
        df_diario=ind_uma["df_diario"],
        df_historico=df_uma,
        origem_dados=None,  # Deve exibir "Origem não informada"
    )
    assert "Origem não informada" in html_uma
    assert "15,00 kW" in html_uma
    html_uma_text = re.sub(r'src="data:image/[^"]+"', '', html_uma)
    assert "NaN" not in html_uma_text
    assert "Infinity" not in html_uma_text

    # 2. Potência zero em toda a série
    df_zero = pd.DataFrame({
        "data_hora": pd.date_range("2026-08-01 00:00", "2026-08-01 05:00", freq="1h"),
        "potencia_kw": [0.0] * 6,
    })
    ind_zero = gerar_indicadores_completos(df_zero, tarifa_kwh=0.75, intervalo_horas=1.0)
    html_zero = construir_conteudo_html(
        indicadores=ind_zero,
        df_diario=ind_zero["df_diario"],
        df_historico=df_zero,
    )
    # Fator de carga com demanda zero deve indicar "Não aplicável"
    assert "Não aplicável" in html_zero

    # 3. Série com lacunas (quebra de linha na curva de carga e células cinza no heatmap)
    df_lacunas = pd.DataFrame({
        "data_hora": pd.to_datetime(["2026-08-01 08:00", "2026-08-01 14:00"]),
        "potencia_kw": [12.0, 18.0],
    })
    b64_curva = gerar_curva_de_carga_base64(df_lacunas, 1.0, 18.0, "2026-08-01 14:00", 15.0)
    assert b64_curva.startswith("data:image/png;base64,")


def test_salvar_relatorio_html_atomico(tmp_path):
    """Testa criação atômica e criação defensiva de diretórios pais."""
    arquivo_destino = tmp_path / "subdiretorio" / "relatorio.html"
    conteudo = "<html><body><h1>Teste PowerMonitor</h1></body></html>"

    salvar_relatorio_html(conteudo, arquivo_destino)
    assert arquivo_destino.exists()
    assert arquivo_destino.read_text(encoding="utf-8") == conteudo

    # Não deve deixar arquivo temporário sobrando
    temp_restante = list(arquivo_destino.parent.glob("*.tmp"))
    assert len(temp_restante) == 0


def test_pipeline_e2e_com_html_customizado(tmp_path):
    """Executa o pipeline completo ponta a ponta validando geração de CSV e HTML com flags CLI."""
    temp_csv = tmp_path / "medicoes.csv"
    temp_db = tmp_path / "power.db"
    temp_csv_out = tmp_path / "saida.csv"
    temp_html_out = tmp_path / "relatorio_final.html"

    # Criar CSV de 24 horas contínuas
    ts = pd.date_range("2026-08-01 00:00", "2026-08-01 23:00", freq="1h")
    linhas = ["data_hora,potencia_kw"] + [f"{t.strftime('%Y-%m-%d %H:%M')},12.5" for t in ts]
    temp_csv.write_text("\n".join(linhas), encoding="utf-8")

    status = main.executar_pipeline(
        csv_path=temp_csv,
        tarifa_kwh=0.80,
        database_path=temp_db,
        output_path=temp_csv_out,
        intervalo_horas=1.0,
        html_path=temp_html_out,
        origem_dados="reais",
    )

    assert status == 0
    assert temp_db.exists()
    assert temp_csv_out.exists()
    assert temp_html_out.exists()

    html_content = temp_html_out.read_text(encoding="utf-8")
    assert "Dados Reais de Medição" in html_content
    assert "12,50 kW" in html_content
    assert "PowerMonitor" in html_content


def test_resolucao_15_minutos_ajusta_rotulos_html(tmp_path):
    """Verifica adaptação de rótulos do HTML para passo de 15 minutos (0.25h)."""
    temp_csv = tmp_path / "medicoes_15min.csv"
    temp_db = tmp_path / "power_15m.db"
    temp_csv_out = tmp_path / "saida_15m.csv"
    temp_html_out = tmp_path / "relatorio_15m.html"

    ts = pd.date_range("2026-08-01 08:00", "2026-08-01 09:45", freq="15min")
    linhas = ["data_hora,potencia_kw"] + [f"{t.strftime('%Y-%m-%d %H:%M')},14.0" for t in ts]
    temp_csv.write_text("\n".join(linhas), encoding="utf-8")

    status = main.executar_pipeline(
        csv_path=temp_csv,
        tarifa_kwh=0.75,
        database_path=temp_db,
        output_path=temp_csv_out,
        intervalo_horas=0.25,
        html_path=temp_html_out,
        origem_dados="simulados",
    )

    assert status == 0
    html_content = temp_html_out.read_text(encoding="utf-8")
    assert "Pico, 15 min" in html_content
    assert "0.25 h (15 min)" in html_content


def test_falha_gravacao_html_retorna_erro_sem_reversao(tmp_path, monkeypatch):
    """Verifica que erro na gravação do HTML retorna código 1 sem dizer que o banco falhou."""
    import src.html_report

    temp_csv = tmp_path / "medicoes.csv"
    temp_db = tmp_path / "power.db"
    temp_csv_out = tmp_path / "saida.csv"
    temp_html_out = tmp_path / "relatorio.html"

    temp_csv.write_text("data_hora,potencia_kw\n2026-08-01 08:00,10.0\n", encoding="utf-8")

    def mock_salvar_falha(conteudo, path):
        raise RuntimeError("Disco cheio simulado")

    monkeypatch.setattr(main, "salvar_relatorio_html", mock_salvar_falha)

    status = main.executar_pipeline(
        csv_path=temp_csv,
        tarifa_kwh=0.75,
        database_path=temp_db,
        output_path=temp_csv_out,
        intervalo_horas=1.0,
        html_path=temp_html_out,
    )

    # Deve retornar 1 (erro)
    assert status == 1
    # O banco e o CSV foram criados antes da falha do HTML
    assert temp_db.exists()
    assert temp_csv_out.exists()

