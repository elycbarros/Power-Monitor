"""Módulo de exibição e exportação de relatórios do PowerMonitor.

Responsabilidades deste módulo (Camada de Apresentação):
- Converter dados analíticos brutos em informação legível para seres humanos e sistemas externos.
- Exibir relatório formatado no terminal com padrão numérico brasileiro (separador de milhar '.' e decimal ',').
- Renderizar tabelas alinhadas com indicadores operacionais e alertas de qualidade de dados.
- Exportar série histórica diária consolidada para arquivo CSV externo.

Conceitos de Programação e Engenharia de Software aplicados:
- 'Separação de Responsabilidades' (SoC): A análise calcula números puros (`analysis.py`),
  o banco armazena (`database.py`), e este módulo cuida estritamente da saída visual/arquivo.
  Mudanças de leiaute ou formato numérico não afetam os cálculos físicos nem os testes analíticos.
- 'Swap de caracteres sem colisão': Troca de '.' e ',' em strings usando marcador intermediário.
- 'Defensive I/O': Criação automática de diretórios pais (`mkdir(parents=True, exist_ok=True)`)
  e tratamento de erros com encadeamento de exceções (`raise ... from e`).
"""

from pathlib import Path
from typing import Dict, Any, Union, Optional, List
import pandas as pd
from src.analysis import IndicadoresCompletosDict


def formatar_numero_br(valor: float, casas_decimais: int = 2) -> str:
    """Formata um float no padrão numérico brasileiro (1.234,56).

    Analogia & Necessidade:
        Em normas técnicas da ABNT e faturas de energia no Brasil, utiliza-se a vírgula
        como separador decimal e o ponto para milhares. Em Python (e padrão anglo-saxão),
        ocorre o inverso (1,234.56).

    Conceito de Programação:
        Técnica de swap sem colisão (Três Passos):
        Se substituíssemos ',' por '.' diretamente, e depois '.' por ',', todos os pontos
        virariam vírgulas (ex: 1,234.56 -> 1.234.56 -> 1,234,56).
        Por isso, usa-se um caractere intermediário neutro ('X'):
        1. ',' -> 'X'  => "1X234.56"
        2. '.' -> ','  => "1X234,56"
        3. 'X' -> '.'  => "1.234,56"

    Args:
        valor: Número em ponto flutuante a ser formatado.
        casas_decimais: Quantidade de dígitos após a vírgula (default 2).

    Returns:
        String formatada (ex: 1500.5 -> "1.500,50").
    """
    formato = f"{{:,.{casas_decimais}f}}"
    texto = formato.format(valor)
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def exibir_relatorio_terminal(
    indicadores: Union[IndicadoresCompletosDict, Dict[str, Any]],
    df_diario: pd.DataFrame,
    estatisticas_lote: Optional[Dict[str, int]] = None,
    avisos_lote: Optional[List[str]] = None,
    avisos_historico: Optional[List[str]] = None,
    intervalo_horas: float = 1.0,
) -> None:
    """Exibe no terminal os resultados consolidados do histórico com rigor técnico.

    Analogia com Engenharia Elétrica:
        Equivale à emissão do laudo técnico de inspeção de medição:
        - Demonstração do fluxo de auditoria metrológica (linhas lidas vs válidas vs descartadas);
        - Consolidação temporal (período total, taxa de cobertura, intervalos ausentes);
        - Grandezas elétricas fundamentais (potência média, pico de demanda e respectivo horário);
        - Fator de carga acompanhado da ressalva de engenharia (modulação vs eficiência);
        - Tabela diária com segregação explícita de dias completos (24h) e parciais;
        - Síntese executiva orientada a investigação operacional.

    Conceito de Programação:
        - Apresentação Amigável e Alinhamento: Utiliza f-strings com especificadores de
          largura e alinhamento (`{dia:<12} | {meds:<10}`) para tabular dados no terminal
          sem depender de bibliotecas externas pesadas (como tabulate).
        - Tratamento de Dados Ausentes: Se o banco estiver vazio, exibe mensagem clara
          e encerra a função sem levantar exceção desnecessária.

    Args:
        indicadores: Dicionário contendo os indicadores técnicos do histórico consolidado.
        df_diario: DataFrame com o resumo diário de consumo e demanda.
        estatisticas_lote: Dicionário opcional com a contabilidade da importação atual.
        avisos_lote: Lista opcional de mensagens de anomalias no arquivo CSV atual.
        avisos_historico: Lista opcional de avisos sobre a série histórica (ex: lacunas no banco).
        intervalo_horas: Resolução amostral da medição em horas (default 1.0h).
    """
    separador_duplo = "=" * 76
    separador_simples = "-" * 76

    print("\n" + separador_duplo)
    print("                      P O W E R M O N I T O R                       ")
    print("       Análise de Consumo e Demanda de Energia Elétrica (v1.0)       ")
    print("                 Desenvolvido por Eng. Ely Barros                   ")
    print(separador_duplo)

    if estatisticas_lote:
        print("\n[FLUXO DA EXECUÇÃO ATUAL]")
        print(f"Linhas lidas no CSV:           {estatisticas_lote.get('total_lidos', 0)}")
        print(f"Medições válidas no lote:      {estatisticas_lote.get('registros_validos', 0)}")
        print(f"Linhas descartadas:            {estatisticas_lote.get('linhas_descartadas', 0)}")
        print(f"Novas medições inseridas:      {estatisticas_lote.get('novos_inseridos', 0)}")

    if indicadores.get("total_medicoes", 0) == 0:
        print("\nNenhum registro disponível no banco de dados para exibir no relatório.")
        print(separador_duplo + "\n")
        return

    p_inicio = indicadores.get("periodo_inicio", "N/D")
    p_fim = indicadores.get("periodo_fim", "N/D")
    total_med = indicadores.get("total_medicoes", 0)

    pot_media = formatar_numero_br(indicadores.get("potencia_media_kw", 0.0), 2)
    demanda_max = formatar_numero_br(indicadores.get("demanda_maxima_kw", 0.0), 2)
    horario_max = indicadores.get("horario_demanda_maxima", "N/D")
    energia_tot = formatar_numero_br(indicadores.get("consumo_total_kwh", 0.0), 2)
    tarifa_fmt = formatar_numero_br(indicadores.get("tarifa_kwh", 0.0), 2)
    custo_tot = formatar_numero_br(indicadores.get("custo_estimado_reais", 0.0), 2)

    # Cobertura
    cobertura = indicadores.get("cobertura", {})
    h_medidas = cobertura.get("horas_medidas", total_med)
    h_esperadas = cobertura.get("horas_esperadas", total_med)
    pct_cob = cobertura.get("percentual_cobertura")
    cob_str = f"{formatar_numero_br(pct_cob, 1)}%" if pct_cob is not None else "N/D"

    # Fator de Carga
    fc_pct = indicadores.get("fator_carga_percentual")
    fc_str = f"{formatar_numero_br(fc_pct, 2)}%" if fc_pct is not None else "Não aplicável (demanda máxima nula)"

    # Dia de Maior Consumo
    dia_max = indicadores.get("dia_maior_consumo", "N/D")
    dia_max_fmt = dia_max
    if dia_max and "-" in dia_max:
        p = dia_max.split("-")
        if len(p) == 3:
            dia_max_fmt = f"{p[2]}/{p[1]}/{p[0]}"
    consumo_dia_max = formatar_numero_br(indicadores.get("consumo_maior_dia_kwh", 0.0), 2)
    dia_max_comp = indicadores.get("dia_maior_consumo_completo", True)
    rotulo_dia_max = "Dia de maior consumo registrado:"
    nota_dia_max = "" if dia_max_comp else " (cobertura parcial)"

    print("\n[HISTÓRICO CONSOLIDADO NO BANCO SQLITE]")
    print(f"Total de medições no histórico: {total_med}")
    print(f"Período temporal coberto:       {p_inicio} a {p_fim}")
    unidade_passos = "horas esperadas" if intervalo_horas == 1.0 else "intervalos esperados"
    print(f"Cobertura temporal:             {h_medidas} de {h_esperadas} {unidade_passos} ({cob_str})\n")

    if intervalo_horas == 1.0:
        rotulo_pot_media = "Potência média horária:"
        rotulo_demanda_max = "Maior potência média horária (demanda de pico):"
    else:
        minutos_passo = int(round(intervalo_horas * 60))
        rotulo_pot_media = f"Potência média (intervalo de {minutos_passo} min):"
        rotulo_demanda_max = f"Maior potência média (demanda de pico, intervalo de {minutos_passo} min):"

    print(f"{rotulo_pot_media}\n  {pot_media} kW\n")
    print(f"{rotulo_demanda_max}\n  {demanda_max} kW")
    print(f"Horário da ocorrência de pico:\n  {horario_max}\n")
    print(f"Fator de carga da instalação:\n  {fc_str}")
    print("  (relação potência média / pico; indica uniformidade, não eficiência)\n")
    print(f"Energia consumida estimada no período:\n  {energia_tot} kWh")
    print(f"{rotulo_dia_max}\n  {dia_max_fmt} ({consumo_dia_max} kWh{nota_dia_max})\n")
    print(f"Simulação de custo (estimativa simplificada; não constitui fatura):\n  R$ {custo_tot} (tarifa didática de referência: R$ {tarifa_fmt}/kWh)\n")

    if avisos_lote:
        print(separador_simples)
        print("AVISOS DA IMPORTAÇÃO ATUAL (CSV):")
        for aviso in avisos_lote:
            print(f"  * {aviso}")
        print()

    if avisos_historico:
        print(separador_simples)
        print("AVISOS DO HISTÓRICO CONSOLIDADO (BANCO DE DADOS):")
        for aviso in avisos_historico:
            print(f"  * {aviso}")
        print()

    if not df_diario.empty:
        print(separador_simples)
        print("CONSOLIDAÇÃO DIÁRIA DE CONSUMO E DEMANDA:")
        print(separador_simples)
        header = (
            f"{'Data':<12} | {'Medições':<10} | {'Status':<11} | {'Pot. Média':<12} | "
            f"{'Pico (kW)':<10} | {'Consumo (kWh)':<14} | {'Part. (%)':<9}"
        )
        print(header)
        print("-" * len(header))
        for _, row in df_diario.iterrows():
            dia = str(row.get("dia", ""))
            meds = str(row.get("total_medicoes", ""))
            completo = row.get("dia_completo", True)
            status_dia = "24h (OK)" if completo else f"{meds}h (Parcial)"
            pm = formatar_numero_br(float(row.get("potencia_media_kw", 0.0)), 2) + " kW"
            dm = formatar_numero_br(float(row.get("demanda_maxima_kw", 0.0)), 2)
            ck = formatar_numero_br(float(row.get("consumo_kwh", 0.0)), 2)
            part_val = row.get("participacao_percentual")
            part_str = (
                f"{formatar_numero_br(float(part_val), 2)}%"
                if part_val is not None and not pd.isna(part_val)
                else "N/A"
            )
            print(f"{dia:<12} | {meds:<10} | {status_dia:<11} | {pm:<12} | {dm:<10} | {ck:<14} | {part_str:<9}")

    # Síntese Executiva
    from src.analysis import gerar_sintese_executiva

    sintese = gerar_sintese_executiva(
        indicadores=indicadores,
        df_diario=df_diario,
        tem_lacunas=bool(avisos_historico or (cobertura and cobertura.get("horas_ausentes", 0) > 0)),
    )
    print("\n" + separador_simples)
    print("SÍNTESE DOS RESULTADOS E RECOMENDAÇÃO TÉCNICA:")
    print(separador_simples)
    print(sintese)

    print("\n" + separador_duplo)
    print("NOTAS DE ENGENHARIA ELÉTRICA E LIMITAÇÕES REGULATÓRIAS:")
    print("1. O pico refere-se à maior potência média no intervalo amostral (Δt).")
    print("   Não equivale à demanda faturável ou contratada de concessionária (REN ANEEL nº 1.000/2021, Art. 2º, XIII).")
    print("2. O fator de carga (Art. 2º, XIX) reflete a uniformidade do perfil frente ao pico registrado.")
    print("   Não se confunde com o fator de potência (cos φ, Art. 302) nem com eficiência de equipamentos.")
    print("3. A estimativa financeira é uma simulação linear simplificada para fins educacionais.")
    print("   Não constitui fatura regulada: não inclui demanda em R$/kW, custo de disponibilidade,")
    print("   faixas horárias de Tarifa Branca (Art. 212), bandeiras tarifárias ou tributos.")
    print("4. Para dias parciais, o consumo contabiliza estritamente os intervalos registrados.")
    print("5. Diferenças na soma das participações diárias decorrem de arredondamentos (ex: 99,99% ou 100,01%).")
    print(separador_duplo + "\n")


def exportar_relatorio_csv(
    indicadores: Union[IndicadoresCompletosDict, Dict[str, Any]],
    df_diario: pd.DataFrame,
    output_path: Union[str, Path],
) -> None:
    """Exporta os indicadores consolidados diários para um arquivo CSV estruturado.

    Analogia com Engenharia Elétrica:
        Gera um arquivo de dados tabular padronizado para exportação, compatível com
        planilhas de faturamento (Excel), sistemas de BI (PowerBI/Grafana) ou auditorias
        externas de eficiência energética.

    Conceito de Programação:
        - Manipulação de Caminhos com 'pathlib.Path': Permite tratar caminhos de arquivos
          de forma independente do sistema operacional (Windows usa '\\', Unix usa '/').
        - 'mkdir(parents=True, exist_ok=True)': Criação defensiva de diretórios.
          Se a pasta 'reports/' ainda não existir, ela é criada no momento da gravação,
          evitando erros do tipo 'FileNotFoundError'.
        - 'raise ... from e' (Exception Chaining): Técnica que preserva o traceback original
          do Python (causa raiz do erro de I/O) enquanto disponibiliza uma mensagem de alto
          nível clara ('RuntimeError') para o usuário final.

    Args:
        indicadores: Dicionário contendo os indicadores técnicos consolidados.
        df_diario: DataFrame com o histórico diário de consumo.
        output_path: Caminho (string ou Path) do arquivo CSV de destino.

    Raises:
        RuntimeError: Se houver falha de escrita no disco (permissão, disco cheio, etc.).
    """
    path = Path(output_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        if not df_diario.empty:
            df_export = df_diario.copy()
            df_export["tarifa_aplicada_r_kwh"] = indicadores.get("tarifa_kwh", 0.0)
            df_export["custo_estimado_dia_r"] = (
                df_export["consumo_kwh"] * indicadores.get("tarifa_kwh", 0.0)
            ).round(2)
            cols = [
                "dia",
                "total_medicoes",
                "dia_completo",
                "potencia_media_kw",
                "demanda_maxima_kw",
                "consumo_kwh",
                "participacao_percentual",
                "tarifa_aplicada_r_kwh",
                "custo_estimado_dia_r",
            ]
            cols_existentes = [c for c in cols if c in df_export.columns]
            df_export[cols_existentes].to_csv(path, index=False)
        else:
            df_export = pd.DataFrame([indicadores])
            df_export.to_csv(path, index=False)
    except Exception as e:
        raise RuntimeError(f"Erro ao salvar relatório CSV em '{path}': {e}") from e
