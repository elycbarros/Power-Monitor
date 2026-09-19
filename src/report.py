"""Módulo de exibição e exportação de relatórios do PowerMonitor."""

from pathlib import Path
from typing import Dict, Any, Union
import pandas as pd


def formatar_numero_br(valor: float, casas_decimais: int = 2) -> str:
    """Formata um float no padrão numérico brasileiro (1.234,56)."""
    formato = f"{{:,.{casas_decimais}f}}"
    texto = formato.format(valor)
    # Inverter separadores: vírgula vira temporária, ponto vira vírgula, temporária vira ponto
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def exibir_relatorio_terminal(
    indicadores: Dict[str, Any], df_diario: pd.DataFrame
) -> None:
    """Exibe no terminal os resultados formatados no padrão esperado do projeto."""
    separador_duplo = "=" * 70
    separador_simples = "-" * 70

    print("\n" + separador_duplo)
    print("                    P O W E R M O N I T O R                   ")
    print("        Análise de Consumo e Demanda de Energia Elétrica      ")
    print(separador_duplo)

    if indicadores.get("total_medicoes", 0) == 0:
        print("\nNenhum registro disponível para exibir no relatório.")
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

    print(f"\nPeríodo analisado:\n{p_inicio} a {p_fim}\n")
    print(f"Medições processadas:\n{total_med}\n")
    print(f"Potência média:\n{pot_media} kW\n")
    print(f"Demanda máxima:\n{demanda_max} kW\n")
    print(f"Horário da demanda máxima:\n{horario_max}\n")
    print(f"Energia estimada:\n{energia_tot} kWh\n")
    print(f"Custo estimado:\nR$ {custo_tot} (tarifa de simulação: R$ {tarifa_fmt}/kWh)\n")

    if not df_diario.empty:
        print(separador_simples)
        print("RESUMO DE CONSUMO DIÁRIO:")
        print(separador_simples)
        header = f"{'Data':<12} | {'Medições':<8} | {'Pot. Média (kW)':<16} | {'Demanda Máx (kW)':<16} | {'Consumo (kWh)':<14}"
        print(header)
        print("-" * len(header))
        for _, row in df_diario.iterrows():
            dia = str(row.get("dia", ""))
            meds = str(row.get("total_medicoes", ""))
            pm = formatar_numero_br(float(row.get("potencia_media_kw", 0.0)), 2)
            dm = formatar_numero_br(float(row.get("demanda_maxima_kw", 0.0)), 2)
            ck = formatar_numero_br(float(row.get("consumo_kwh", 0.0)), 2)
            print(f"{dia:<12} | {meds:<8} | {pm:<16} | {dm:<16} | {ck:<14}")

    print("\n" + separador_duplo)
    print("Observação:")
    print("Resultados calculados a partir de dados simulados para fins educacionais.")
    print("Os valores acima não representam faturamento real de concessionária.")
    print(separador_duplo + "\n")


def exportar_relatorio_csv(
    indicadores: Dict[str, Any],
    df_diario: pd.DataFrame,
    output_path: Union[str, Path],
) -> None:
    """Exporta o relatório consolidado diário para um arquivo CSV.

    Garante que a pasta de destino exista antes de salvar.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Se houver dados diários, exportamos o DataFrame diário enriquecido com colunas de resumo
        if not df_diario.empty:
            df_export = df_diario.copy()
            df_export["tarifa_aplicada_r_kwh"] = indicadores.get("tarifa_kwh", 0.0)
            df_export["custo_estimado_dia_r"] = (
                df_export["consumo_kwh"] * indicadores.get("tarifa_kwh", 0.0)
            ).round(2)
            df_export.to_csv(path, index=False)
        else:
            # Caso contrário, salva um arquivo com os indicadores gerais
            df_export = pd.DataFrame([indicadores])
            df_export.to_csv(path, index=False)
    except Exception as e:
        raise RuntimeError(f"Erro ao salvar relatório CSV em '{path}': {e}") from e
