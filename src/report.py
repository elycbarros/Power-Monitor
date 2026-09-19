"""Módulo de exibição e exportação de relatórios do PowerMonitor."""

from pathlib import Path
from typing import Dict, Any, Union, Optional, List
import pandas as pd
from src.analysis import IndicadoresCompletosDict


def formatar_numero_br(valor: float, casas_decimais: int = 2) -> str:
    """Formata um float no padrão numérico brasileiro (1.234,56)."""
    formato = f"{{:,.{casas_decimais}f}}"
    texto = formato.format(valor)
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def exibir_relatorio_terminal(
    indicadores: Union[IndicadoresCompletosDict, Dict[str, Any]],
    df_diario: pd.DataFrame,
    estatisticas_lote: Optional[Dict[str, int]] = None,
    avisos_lote: Optional[List[str]] = None,
    avisos_historico: Optional[List[str]] = None,
) -> None:
    """Exibe no terminal os resultados consolidados do histórico com clareza e

    rigor técnico.
    """
    separador_duplo = "=" * 76
    separador_simples = "-" * 76

    print("\n" + separador_duplo)
    print("                      P O W E R M O N I T O R                       ")
    print("       Análise de Consumo e Demanda de Energia Elétrica (v1.0)       ")
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
    print(f"Cobertura temporal:             {h_medidas} de {h_esperadas} horas esperadas ({cob_str})\n")

    print(f"Potência média horária:\n  {pot_media} kW\n")
    print(f"Maior potência média horária (demanda de pico):\n  {demanda_max} kW")
    print(f"Horário da ocorrência de pico:\n  {horario_max}\n")
    print(f"Fator de carga da instalação:\n  {fc_str}")
    print("  (relação potência média / pico; indica uniformidade, não eficiência)\n")
    print(f"Energia consumida estimada no período:\n  {energia_tot} kWh")
    print(f"{rotulo_dia_max}\n  {dia_max_fmt} ({consumo_dia_max} kWh{nota_dia_max})\n")
    print(f"Custo financeiro estimado (simulação simplificada):\n  R$ {custo_tot} (tarifa de referência: R$ {tarifa_fmt}/kWh)\n")

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
    print("NOTAS DE ENGENHARIA ELÉTRICA E LIMITAÇÕES:")
    print("1. O pico refere-se à maior potência média horária registrada no histórico.")
    print("   Não equivale à demanda contratada ou de faturamento regulada por concessionárias.")
    print("2. O fator de carga reflete a uniformidade do perfil de consumo frente à capacidade de pico.")
    print("   Não representa a eficiência dos aparelhos nem deve ser rotulado sem contexto operacional.")
    print("3. Para dias parciais, o consumo contabiliza estritamente os intervalos registrados.")
    print("4. Diferenças na soma das participações diárias decorrem de arredondamentos (ex: 99,99% ou 100,01%).")
    print("5. O custo financeiro é uma estimativa linear simples sem tarifas horossazonais.")
    print(separador_duplo + "\n")


def exportar_relatorio_csv(
    indicadores: Union[IndicadoresCompletosDict, Dict[str, Any]],
    df_diario: pd.DataFrame,
    output_path: Union[str, Path],
) -> None:
    """Exporta o relatório consolidado diário para um arquivo CSV.

    Garante que a pasta de destino exista antes de salvar.
    Lança RuntimeError caso a operação de gravação falhe.
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
