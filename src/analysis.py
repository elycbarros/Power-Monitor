"""Módulo de análise de dados e cálculo de indicadores de consumo e demanda."""

import math
from typing import Tuple, Optional, Dict, Any, TypedDict, Union
import pandas as pd


class CoberturaDict(TypedDict):
    """Estrutura tipada do resumo de cobertura temporal das medições."""
    horas_medidas: int
    horas_esperadas: int
    horas_ausentes: int
    percentual_cobertura: Optional[float]


class IndicadoresCompletosDict(TypedDict):
    """Estrutura tipada do conjunto completo de indicadores técnicos consolidados."""
    total_medicoes: int
    periodo_inicio: Optional[str]
    periodo_fim: Optional[str]
    potencia_media_kw: float
    demanda_maxima_kw: float
    horario_demanda_maxima: Optional[str]
    consumo_total_kwh: float
    tarifa_kwh: float
    custo_estimado_reais: float
    fator_carga: Optional[float]
    fator_carga_percentual: Optional[float]
    dia_maior_consumo: Optional[str]
    consumo_maior_dia_kwh: float
    dia_maior_consumo_completo: bool
    cobertura: CoberturaDict
    df_diario: pd.DataFrame


def validar_intervalo_horas(intervalo_horas: float) -> None:
    """Valida se o intervalo de tempo informado é finito e estritamente positivo (> 0)."""
    if not isinstance(intervalo_horas, (int, float)) or not math.isfinite(intervalo_horas) or intervalo_horas <= 0:
        raise ValueError(
            f"Intervalo de medição inválido: {intervalo_horas}. "
            f"Deve ser um número numérico finito e estritamente positivo (> 0)."
        )


def calcular_potencia_media(df: pd.DataFrame) -> float:
    """Calcula a potência média registrada no período em kW.

    Retorna 0.0 caso o DataFrame esteja vazio.
    """
    if df.empty or "potencia_kw" not in df.columns:
        return 0.0
    return float(df["potencia_kw"].mean())


def calcular_demanda_maxima(df: pd.DataFrame) -> Tuple[float, Optional[str]]:
    """Identifica a maior demanda de potência registrada (kW) e o respectivo

    carimbo de data e hora formatado.

    Em caso de empate na potência máxima, adota o critério determinístico de
    selecionar a ocorrência cronologicamente mais antiga.

    Retorna:
        Tuple[float, Optional[str]]: (demanda_maxima_kw, data_hora_formatada)
        Caso esteja vazio, retorna (0.0, None).
    """
    if df.empty or "potencia_kw" not in df.columns or "data_hora" not in df.columns:
        return 0.0, None

    df_calc = df.copy()
    df_calc["data_hora"] = pd.to_datetime(df_calc["data_hora"])
    # Ordenar por potência decrescente e data_hora crescente para desempate determinístico
    df_sorted = df_calc.sort_values(["potencia_kw", "data_hora"], ascending=[False, True])
    row_max = df_sorted.iloc[0]

    demanda_max = float(row_max["potencia_kw"])
    dt_val = row_max["data_hora"]
    dt_str = dt_val.strftime("%d/%m/%Y %H:%M")

    return demanda_max, dt_str


def calcular_consumo_total(df: pd.DataFrame, intervalo_horas: float = 1.0) -> float:
    """Calcula a energia elétrica total estimada consumida no período em kWh.

    Premissa de Engenharia Elétrica:
    A energia (kWh) é a integral da potência no tempo. Considerando que cada
    amostra representa a potência média demandada durante um intervalo regular
    Δt (horas):
        Energia (kWh) = Σ (potencia_kw * intervalo_horas)

    Retorna 0.0 caso o DataFrame esteja vazio.
    """
    validar_intervalo_horas(intervalo_horas)

    if df.empty or "potencia_kw" not in df.columns:
        return 0.0

    return float((df["potencia_kw"] * intervalo_horas).sum())


def calcular_consumo_diario(df: pd.DataFrame, intervalo_horas: float = 1.0) -> pd.DataFrame:
    """Agrupa as medições por dia e calcula os indicadores diários de consumo e
    demanda:
    - dia (YYYY-MM-DD)
    - total_medicoes
    - dia_completo (True se possuir a quantidade exata de medições esperadas para 24h)
    - potencia_media_kw
    - demanda_maxima_kw
    - consumo_kwh
    - participacao_percentual (fração em % do consumo diário frente à energia total registrada)

    Nota: Dias incompletos contabilizam o consumo apenas dos intervalos registrados.
    """
    validar_intervalo_horas(intervalo_horas)

    cols = [
        "dia",
        "total_medicoes",
        "dia_completo",
        "potencia_media_kw",
        "demanda_maxima_kw",
        "consumo_kwh",
        "participacao_percentual",
    ]
    if df.empty or "potencia_kw" not in df.columns or "data_hora" not in df.columns:
        return pd.DataFrame(columns=cols)

    df_calc = df.copy()
    df_calc["data_hora"] = pd.to_datetime(df_calc["data_hora"])
    df_calc["dia"] = df_calc["data_hora"].dt.date
    df_calc["energia_kwh_bruta"] = df_calc["potencia_kw"] * intervalo_horas

    # Quantidade esperada de medições em 24h para o intervalo dado
    medicoes_esperadas_dia = round(24.0 / intervalo_horas)

    agrupado = (
        df_calc.groupby("dia")
        .agg(
            total_medicoes=("potencia_kw", "count"),
            potencia_media_kw=("potencia_kw", "mean"),
            demanda_maxima_kw=("potencia_kw", "max"),
            consumo_kwh_bruto=("energia_kwh_bruta", "sum"),
        )
        .reset_index()
    )

    consumo_total_periodo = df_calc["energia_kwh_bruta"].sum()

    agrupado["dia"] = agrupado["dia"].astype(str)
    agrupado["dia_completo"] = agrupado["total_medicoes"] == medicoes_esperadas_dia
    agrupado["potencia_media_kw"] = agrupado["potencia_media_kw"].round(2)
    agrupado["demanda_maxima_kw"] = agrupado["demanda_maxima_kw"].round(2)
    agrupado["consumo_kwh"] = agrupado["consumo_kwh_bruto"].round(2)

    if consumo_total_periodo > 0:
        agrupado["participacao_percentual"] = (
            (agrupado["consumo_kwh_bruto"] / consumo_total_periodo) * 100.0
        ).round(2)
    else:
        agrupado["participacao_percentual"] = None

    return agrupado[cols]


def calcular_fator_carga(potencia_media_kw: float, demanda_maxima_kw: float) -> Optional[float]:
    """Calcula o Fator de Carga (FC) da instalação.

    Fórmula: FC = potencia_media / demanda_maxima
    Indica a uniformidade da curva de carga ao longo do tempo.
    Não representa nem deve ser confundido com a eficiência energética dos equipamentos.

    Retorna None ('não aplicável') caso a demanda máxima seja menor ou igual a zero ou não finita.
    """
    if (
        not isinstance(potencia_media_kw, (int, float))
        or not isinstance(demanda_maxima_kw, (int, float))
        or not math.isfinite(potencia_media_kw)
        or not math.isfinite(demanda_maxima_kw)
        or demanda_maxima_kw <= 0.0
    ):
        return None

    return float(potencia_media_kw / demanda_maxima_kw)


def identificar_dia_maior_consumo(df_diario: pd.DataFrame) -> Tuple[Optional[str], float, bool]:
    """Identifica a data com maior consumo registrado (kWh) e se ela foi um dia completo.

    Em caso de empate no consumo diário, adota o critério determinístico de
    selecionar a data cronologicamente mais antiga (dia ASC).

    Retorna:
        Tuple[Optional[str], float, bool]: (dia_str, consumo_kwh, dia_completo)
        Se df_diario estiver vazio, retorna (None, 0.0, False).
    """
    if df_diario.empty or "consumo_kwh" not in df_diario.columns or "dia" not in df_diario.columns:
        return None, 0.0, False

    df_sorted = df_diario.sort_values(by=["consumo_kwh", "dia"], ascending=[False, True])
    row = df_sorted.iloc[0]
    dia_str = str(row["dia"])
    consumo_kwh = float(row["consumo_kwh"])
    dia_completo = bool(row.get("dia_completo", True))

    return dia_str, consumo_kwh, dia_completo


def calcular_cobertura_medicoes(df: pd.DataFrame, intervalo_horas: float = 1.0) -> CoberturaDict:
    """Calcula a cobertura temporal das medições entre o início da primeira medição
    e o fim da última hora representada.

    No contrato v1 (intervalos regulares de 1h), cada timestamp representa o início
    de uma hora cheia que se estende por intervalo_horas.
    Não supõe que o primeiro e o último dia civis estejam completos.

    Retorna um dicionário com:
    - horas_medidas: quantidade de horas com medições válidas
    - horas_esperadas: total de horas esperadas no período delimitado
    - horas_ausentes: horas ausentes no período delimitado
    - percentual_cobertura: percentual de cobertura (horas_medidas / horas_esperadas * 100)
    """
    validar_intervalo_horas(intervalo_horas)

    if df.empty or "data_hora" not in df.columns:
        return {
            "horas_medidas": 0,
            "horas_esperadas": 0,
            "horas_ausentes": 0,
            "percentual_cobertura": None,
        }

    df_temp = df.copy()
    df_temp["data_hora"] = pd.to_datetime(df_temp["data_hora"])
    df_temp = df_temp.sort_values("data_hora")

    t_min = df_temp["data_hora"].iloc[0]
    t_max = df_temp["data_hora"].iloc[-1]

    segundos_totais = (t_max - t_min).total_seconds()
    intervalo_segundos = intervalo_horas * 3600.0
    passos_esperados = int(round(segundos_totais / intervalo_segundos)) + 1

    horas_medidas = int(df_temp["data_hora"].nunique())
    horas_ausentes = max(0, passos_esperados - horas_medidas)
    percentual_cobertura = round((horas_medidas / passos_esperados) * 100.0, 2) if passos_esperados > 0 else None

    return {
        "horas_medidas": horas_medidas,
        "horas_esperadas": passos_esperados,
        "horas_ausentes": horas_ausentes,
        "percentual_cobertura": percentual_cobertura,
    }


def calcular_custo_estimado(consumo_kwh: float, tarifa_kwh: float) -> float:
    """Calcula a estimativa de custo financeiro em Reais (R$).

    Fórmula simplificada: Custo = Consumo (kWh) * Tarifa (R$/kWh)
    Rejeita valores nulos, negativos ou não finitos (NaN/Inf).
    """
    if not isinstance(consumo_kwh, (int, float)) or not math.isfinite(consumo_kwh) or consumo_kwh < 0:
        raise ValueError("Consumo (kWh) deve ser um número finito e não negativo (>= 0).")

    if not isinstance(tarifa_kwh, (int, float)) or not math.isfinite(tarifa_kwh) or tarifa_kwh < 0:
        raise ValueError("Tarifa (R$/kWh) deve ser um número finito e não negativo (>= 0).")

    return float(consumo_kwh * tarifa_kwh)


def gerar_indicadores_completos(
    df: pd.DataFrame, tarifa_kwh: float, intervalo_horas: float = 1.0
) -> IndicadoresCompletosDict:
    """Gera um dicionário estruturado com todos os indicadores consolidados do
    histórico.
    """
    validar_intervalo_horas(intervalo_horas)

    if df.empty:
        return {
            "total_medicoes": 0,
            "periodo_inicio": None,
            "periodo_fim": None,
            "potencia_media_kw": 0.0,
            "demanda_maxima_kw": 0.0,
            "horario_demanda_maxima": None,
            "consumo_total_kwh": 0.0,
            "tarifa_kwh": tarifa_kwh,
            "custo_estimado_reais": 0.0,
            "fator_carga": None,
            "fator_carga_percentual": None,
            "dia_maior_consumo": None,
            "consumo_maior_dia_kwh": 0.0,
            "dia_maior_consumo_completo": False,
            "cobertura": {
                "horas_medidas": 0,
                "horas_esperadas": 0,
                "horas_ausentes": 0,
                "percentual_cobertura": None,
            },
            "df_diario": pd.DataFrame(
                columns=["dia", "total_medicoes", "potencia_media_kw", "demanda_maxima_kw",
                         "consumo_kwh", "participacao_percentual", "dia_completo"]
            ),
        }

    df_sorted = df.copy()
    df_sorted["data_hora"] = pd.to_datetime(df_sorted["data_hora"])
    df_sorted = df_sorted.sort_values("data_hora").reset_index(drop=True)

    dt_inicio = df_sorted["data_hora"].iloc[0]
    dt_fim = df_sorted["data_hora"].iloc[-1]

    fmt = "%d/%m/%Y"
    str_inicio = dt_inicio.strftime(fmt)
    str_fim = dt_fim.strftime(fmt)

    pot_media = calcular_potencia_media(df_sorted)
    demanda_max, horario_max = calcular_demanda_maxima(df_sorted)
    consumo_total = calcular_consumo_total(df_sorted, intervalo_horas=intervalo_horas)
    custo_estimado = calcular_custo_estimado(consumo_total, tarifa_kwh)

    df_diario = calcular_consumo_diario(df_sorted, intervalo_horas=intervalo_horas)
    dia_max, consumo_dia_max, dia_max_completo = identificar_dia_maior_consumo(df_diario)
    cobertura = calcular_cobertura_medicoes(df_sorted, intervalo_horas=intervalo_horas)
    fc = calcular_fator_carga(pot_media, demanda_max)
    fc_percentual = round(fc * 100.0, 2) if fc is not None else None

    return {
        "total_medicoes": len(df_sorted),
        "periodo_inicio": str_inicio,
        "periodo_fim": str_fim,
        "potencia_media_kw": round(pot_media, 2),
        "demanda_maxima_kw": round(demanda_max, 2),
        "horario_demanda_maxima": horario_max,
        "consumo_total_kwh": round(consumo_total, 2),
        "tarifa_kwh": tarifa_kwh,
        "custo_estimado_reais": round(custo_estimado, 2),
        "fator_carga": round(fc, 4) if fc is not None else None,
        "fator_carga_percentual": fc_percentual,
        "dia_maior_consumo": dia_max,
        "consumo_maior_dia_kwh": consumo_dia_max,
        "dia_maior_consumo_completo": dia_max_completo,
        "cobertura": cobertura,
        # df_diario já calculado internamente; exposto para evitar recálculo no pipeline
        "df_diario": df_diario,
    }


def gerar_sintese_executiva(
    indicadores: Union[IndicadoresCompletosDict, Dict[str, Any]],
    df_diario: pd.DataFrame,
    tem_lacunas: bool = False,
) -> str:
    """Gera uma síntese curta e interpretativa a partir dos indicadores calculados.

    Regras determinísticas e baseadas estritamente em dados:
    - Informa energia registrada e período analisado;
    - Informa dia de maior consumo registrado e cobertura;
    - Informa maior demanda média horária e seu horário;
    - Informa fator de carga com interpretação correta (uniformidade, não eficiência);
    - Trata lacunas e dias parciais sem extrapolações;
    - Formula recomendações técnicas de investigação sem prescrever alterações operacionais ou tarifárias.
    """
    if not indicadores or indicadores.get("total_medicoes", 0) == 0:
        return "Nenhum dado válido disponível no histórico para gerar a síntese executiva."

    p_inicio = indicadores.get("periodo_inicio", "N/D")
    p_fim = indicadores.get("periodo_fim", "N/D")
    tot_med = indicadores.get("total_medicoes", 0)

    # Formatação auxiliar local
    def _fmt(val: Optional[float], decimais: int = 2) -> str:
        if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
            return "N/D"
        formato = f"{{:,.{decimais}f}}"
        return formato.format(val).replace(",", "X").replace(".", ",").replace("X", ".")

    energia_tot = _fmt(indicadores.get("consumo_total_kwh", 0.0), 2)
    pot_media = _fmt(indicadores.get("potencia_media_kw", 0.0), 2)
    demanda_max = _fmt(indicadores.get("demanda_maxima_kw", 0.0), 2)
    horario_max = indicadores.get("horario_demanda_maxima", "N/D")

    cob = indicadores.get("cobertura", {})
    cob_pct = cob.get("percentual_cobertura")
    cob_str = f"{_fmt(cob_pct, 1)}%" if cob_pct is not None else "N/D"
    horas_ausentes = cob.get("horas_ausentes", 0)

    fc_pct = indicadores.get("fator_carga_percentual")
    if fc_pct is not None:
        fc_str = f"{_fmt(fc_pct, 2)}%"
        fc_texto = (
            f"O fator de carga observado foi de {fc_str}, indicando a uniformidade da demanda "
            f"em relação à capacidade de pico (razão entre a potência média de {pot_media} kW e o pico de {demanda_max} kW). "
            f"Esse indicador quantifica o perfil de modulação da carga, não devendo ser confundido com a eficiência energética dos equipamentos."
        )
    else:
        fc_texto = "O fator de carga não é aplicável para este conjunto de dados (demanda máxima nula)."

    if tem_lacunas or horas_ausentes > 0:
        fc_texto += " Por haver horas ausentes no período, o fator de carga e as médias referem-se estritamente às horas disponíveis."

    dia_max = indicadores.get("dia_maior_consumo")
    consumo_dia_max = _fmt(indicadores.get("consumo_maior_dia_kwh", 0.0), 2)
    dia_max_completo = indicadores.get("dia_maior_consumo_completo", True)

    dia_max_fmt = dia_max
    if dia_max and "-" in dia_max:
        partes = dia_max.split("-")
        if len(partes) == 3:
            dia_max_fmt = f"{partes[2]}/{partes[1]}/{partes[0]}"

    part_dia_max_str = ""
    if not df_diario.empty and "participacao_percentual" in df_diario.columns and dia_max:
        row_dia = df_diario[df_diario["dia"] == dia_max]
        if not row_dia.empty:
            val_part = row_dia["participacao_percentual"].iloc[0]
            if val_part is not None and not pd.isna(val_part):
                part_dia_max_str = f" ({_fmt(float(val_part), 2)}% da energia total registrada)"

    nota_dia_parcial = ""
    if not dia_max_completo:
        nota_dia_parcial = " (atenção: dia com cobertura parcial de medições; a comparação com dias completos é limitada)"

    # 1. Volume e Cobertura
    p1 = (
        f"No período de {p_inicio} a {p_fim}, foram contabilizadas {tot_med} medições horárias válidas, "
        f"totalizando um consumo de {energia_tot} kWh com cobertura temporal de {cob_str} "
        f"entre os limites monitorados."
    )
    if horas_ausentes > 0:
        p1 += f" Foram identificadas {horas_ausentes} hora(s) ausente(s) no histórico, sem qualquer preenchimento artificial por zero."

    # 2. Concentração e Pico
    p2 = (
        f"A maior potência média horária foi de {demanda_max} kW registrada em {horario_max}. "
        f"O maior consumo diário registrado ocorreu em {dia_max_fmt}, com {consumo_dia_max} kWh{part_dia_max_str}{nota_dia_parcial}."
    )

    # 3. Fator de Carga
    p3 = fc_texto

    # 4. Investigação Técnica
    p4 = (
        f"Recomendação técnica: Investigar as atividades operacionais e cargas acionadas no intervalo de "
        f"{horario_max} para identificar os fatores que provocaram o pico de demanda, sem inferir "
        f"desperdício ou defeito de equipamentos sem medições de campo adicionais."
    )

    return f"{p1}\n\n{p2}\n\n{p3}\n\n{p4}"
