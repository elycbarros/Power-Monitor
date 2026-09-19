"""Módulo de análise de dados e cálculo de indicadores de consumo e demanda."""

from typing import Tuple, Optional, Dict, Any
import pandas as pd


def calcular_potencia_media(df: pd.DataFrame) -> float:
    """Calcula a potência média registrada no período em kW.

    Retorna 0.0 caso o DataFrame esteja vazio.
    """
    if df.empty or "potencia_kw" not in df.columns:
        return 0.0
    return float(df["potencia_kw"].mean())


def calcular_demanda_maxima(df: pd.DataFrame) -> Tuple[float, Optional[str]]:
    """Identifica a maior demanda de potência registrada (kW) e o respectivo

    carimbo de data e hora.

    Retorna:
        Tuple[float, Optional[str]]: (demanda_maxima_kw, data_hora_formatada)
        Caso esteja vazio, retorna (0.0, None).
    """
    if df.empty or "potencia_kw" not in df.columns or "data_hora" not in df.columns:
        return 0.0, None

    idx_max = df["potencia_kw"].idxmax()
    row_max = df.loc[idx_max]
    demanda_max = float(row_max["potencia_kw"])

    dt_val = row_max["data_hora"]
    dt_str = dt_val.strftime("%d/%m/%Y %H:%M") if hasattr(dt_val, "strftime") else str(dt_val)

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
    if df.empty or "potencia_kw" not in df.columns:
        return 0.0
    return float((df["potencia_kw"] * intervalo_horas).sum())


def calcular_consumo_diario(df: pd.DataFrame, intervalo_horas: float = 1.0) -> pd.DataFrame:
    """Agrupa as medições por dia e calcula os indicadores diários de consumo e

    demanda:
    - dia (YYYY-MM-DD)
    - total_medicoes
    - potencia_media_kw
    - demanda_maxima_kw
    - consumo_kwh
    """
    if df.empty or "potencia_kw" not in df.columns or "data_hora" not in df.columns:
        return pd.DataFrame(
            columns=["dia", "total_medicoes", "potencia_media_kw", "demanda_maxima_kw", "consumo_kwh"]
        )

    df_calc = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df_calc["data_hora"]):
        df_calc["data_hora"] = pd.to_datetime(df_calc["data_hora"])

    df_calc["dia"] = df_calc["data_hora"].dt.date
    df_calc["energia_kwh"] = df_calc["potencia_kw"] * intervalo_horas

    agrupado = (
        df_calc.groupby("dia")
        .agg(
            total_medicoes=("potencia_kw", "count"),
            potencia_media_kw=("potencia_kw", "mean"),
            demanda_maxima_kw=("potencia_kw", "max"),
            consumo_kwh=("energia_kwh", "sum"),
        )
        .reset_index()
    )

    agrupado["dia"] = agrupado["dia"].astype(str)
    agrupado["potencia_media_kw"] = agrupado["potencia_media_kw"].round(2)
    agrupado["demanda_maxima_kw"] = agrupado["demanda_maxima_kw"].round(2)
    agrupado["consumo_kwh"] = agrupado["consumo_kwh"].round(2)

    return agrupado


def calcular_custo_estimado(consumo_kwh: float, tarifa_kwh: float) -> float:
    """Calcula a estimativa de custo financeiro em Reais (R$).

    Fórmula: Custo = Consumo (kWh) * Tarifa (R$/kWh)
    """
    if consumo_kwh < 0 or tarifa_kwh < 0:
        raise ValueError("Consumo e tarifa não podem ser negativos.")
    return float(consumo_kwh * tarifa_kwh)


def gerar_indicadores_completos(
    df: pd.DataFrame, tarifa_kwh: float, intervalo_horas: float = 1.0
) -> Dict[str, Any]:
    """Gera um dicionário estruturado com todos os indicadores consolidados do

    sistema.
    """
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
        }

    df_sorted = df.sort_values("data_hora").reset_index(drop=True)
    dt_inicio = df_sorted["data_hora"].iloc[0]
    dt_fim = df_sorted["data_hora"].iloc[-1]

    fmt = "%d/%m/%Y"
    str_inicio = dt_inicio.strftime(fmt) if hasattr(dt_inicio, "strftime") else str(dt_inicio)[:10]
    str_fim = dt_fim.strftime(fmt) if hasattr(dt_fim, "strftime") else str(dt_fim)[:10]

    pot_media = calcular_potencia_media(df_sorted)
    demanda_max, horario_max = calcular_demanda_maxima(df_sorted)
    consumo_total = calcular_consumo_total(df_sorted, intervalo_horas=intervalo_horas)
    custo_estimado = calcular_custo_estimado(consumo_total, tarifa_kwh)

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
    }
