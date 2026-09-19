"""Módulo de importação e validação de dados de medições elétricas."""

from pathlib import Path
from typing import Tuple, Dict, Any, Union
import pandas as pd


REQUIRED_COLUMNS = ["data_hora", "potencia_kw"]


def load_and_validate_csv(
    file_path: Union[str, Path]
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Carrega o arquivo CSV de medições, aplica validações técnicas e retorna

    os dados válidos juntamente com um relatório de validação.

    Validações realizadas:
    - Existência e integridade do arquivo;
    - Presença das colunas obrigatórias ('data_hora', 'potencia_kw');
    - Conversão para datetime da coluna 'data_hora';
    - Conversão para numérico da coluna 'potencia_kw';
    - Detecção e descarte de valores ausentes (NaN/null);
    - Rejeição de valores negativos de potência elétrica (P < 0);
    - Detecção e tratamento de registros com carimbos de data/hora duplicados.

    Retorna:
        Tuple[pd.DataFrame, Dict[str, Any]]:
            - DataFrame limpo contendo as colunas validadas.
            - Dicionário com estatísticas do processo de validação.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Arquivo de medições não encontrado: '{path}'")

    if path.stat().st_size == 0:
        raise ValueError(f"O arquivo CSV está vazio: '{path}'")

    try:
        df_raw = pd.read_csv(path)
    except Exception as e:
        raise ValueError(f"Falha ao ler o arquivo CSV '{path}': {e}") from e

    # 1. Validação de colunas obrigatórias
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df_raw.columns]
    if missing_cols:
        raise ValueError(
            f"Estrutura incorreta no arquivo CSV. Colunas ausentes: {missing_cols}. "
            f"Colunas esperadas: {REQUIRED_COLUMNS}"
        )

    total_lidos = len(df_raw)
    relatorio: Dict[str, Any] = {
        "total_lidos": total_lidos,
        "registros_validos": 0,
        "ausentes_descartados": 0,
        "invalidos_conversao": 0,
        "negativos_rejeitados": 0,
        "duplicados_descartados": 0,
        "avisos": [],
    }

    if total_lidos == 0:
        relatorio["avisos"].append("Arquivo contém apenas cabeçalhos sem linhas de dados.")
        return pd.DataFrame(columns=REQUIRED_COLUMNS), relatorio

    # Cópia para trabalhar apenas com as colunas relevantes
    df = df_raw[REQUIRED_COLUMNS].copy()

    # 2. Conversão de data_hora para datetime
    df["data_hora_parsed"] = pd.to_datetime(df["data_hora"], errors="coerce")
    invalid_dates = df["data_hora_parsed"].isna()
    if invalid_dates.any():
        qtd_invalid_dates = int(invalid_dates.sum())
        relatorio["invalidos_conversao"] += qtd_invalid_dates
        relatorio["avisos"].append(
            f"{qtd_invalid_dates} registro(s) com formato de data/hora inválido foram descartados."
        )

    # 3. Conversão de potencia_kw para numérico
    df["potencia_kw_parsed"] = pd.to_numeric(df["potencia_kw"], errors="coerce")
    invalid_power = df["potencia_kw_parsed"].isna()
    if invalid_power.any():
        qtd_invalid_power = int(invalid_power.sum())
        relatorio["invalidos_conversao"] += qtd_invalid_power
        relatorio["avisos"].append(
            f"{qtd_invalid_power} registro(s) com valor não numérico ou ausente em potencia_kw foram descartados."
        )

    # Filtrar apenas registros válidos na conversão
    df_valid = df[~invalid_dates & ~invalid_power].copy()

    # 4. Rejeição de potência negativa (regra de engenharia: potência ativa consumida >= 0)
    negativos = df_valid["potencia_kw_parsed"] < 0
    if negativos.any():
        qtd_negativos = int(negativos.sum())
        relatorio["negativos_rejeitados"] += qtd_negativos
        relatorio["avisos"].append(
            f"{qtd_negativos} registro(s) com potência negativa foram rejeitados (potência deve ser >= 0 kW)."
        )
        df_valid = df_valid[~negativos].copy()

    # 5. Tratamento de duplicatas por data_hora
    duplicados = df_valid.duplicated(subset=["data_hora_parsed"], keep="first")
    if duplicados.any():
        qtd_duplicados = int(duplicados.sum())
        relatorio["duplicados_descartados"] += qtd_duplicados
        relatorio["avisos"].append(
            f"{qtd_duplicados} registro(s) duplicados para a mesma data/hora foram descartados."
        )
        df_valid = df_valid[~duplicados].copy()

    # Preparar DataFrame final limpo
    df_final = pd.DataFrame(
        {
            "data_hora": df_valid["data_hora_parsed"],
            "potencia_kw": df_valid["potencia_kw_parsed"].astype(float),
        }
    ).sort_values("data_hora").reset_index(drop=True)

    relatorio["registros_validos"] = len(df_final)

    return df_final, relatorio
