"""Módulo de importação e validação de dados de medições elétricas."""

import math
import re
from pathlib import Path
from typing import Tuple, Dict, Any, Union, List
import pandas as pd


REQUIRED_COLUMNS = ["data_hora", "potencia_kw"]


def identificar_lacunas_temporais(
    df: pd.DataFrame, intervalo_horas: float = 1.0
) -> List[pd.Timestamp]:
    """Identifica medições ausentes na série temporal entre a primeira e a última
    medição registrada para o intervalo regular configurado.

    Não supõe interpolação nem preenchimento com zeros.
    """
    if df.empty or len(df) < 2 or "data_hora" not in df.columns:
        return []

    serie_temporal = pd.to_datetime(df["data_hora"]).sort_values().drop_duplicates()
    inicio = serie_temporal.iloc[0]
    fim = serie_temporal.iloc[-1]

    minutos_intervalo = int(round(intervalo_horas * 60))
    if minutos_intervalo <= 0:
        minutos_intervalo = 60
    freq = f"{minutos_intervalo}min" if minutos_intervalo < 60 else f"{int(round(intervalo_horas))}h"
    grade_esperada = pd.date_range(inicio, fim, freq=freq)
    grade_presente = pd.DatetimeIndex(serie_temporal)
    horas_faltantes = grade_esperada.difference(grade_presente)

    return list(horas_faltantes)


def formatar_resumo_lacunas(
    lacunas: List[pd.Timestamp], intervalo_horas: float = 1.0
) -> List[str]:
    """Resume uma lista de timestamps ausentes agrupando dias completos e
    apresentando exemplos sem poluir a saída com listagens extensas.
    """
    if not lacunas:
        return []

    s_lacunas = pd.Series(lacunas)
    por_dia = s_lacunas.groupby(s_lacunas.dt.date).count()

    passos_por_dia = int(round(24.0 / intervalo_horas))
    mensagens = []
    dias_completos = por_dia[por_dia == passos_por_dia].index.tolist()
    dias_parciais = por_dia[por_dia < passos_por_dia]

    rotulo_passos = "24h" if intervalo_horas == 1.0 else f"{passos_por_dia} medições (24h)"

    if dias_completos:
        dias_str = ", ".join(d.strftime("%d/%m/%Y") for d in dias_completos[:3])
        if len(dias_completos) > 3:
            dias_str += f" e mais {len(dias_completos) - 3} dia(s)"
        mensagens.append(f"Dia(s) inteiramente ausente(s) ({rotulo_passos}): {dias_str}.")

    unidade = "hora(s)" if intervalo_horas == 1.0 else "medição(ões)"
    for dia, qtd in dias_parciais.items():
        mensagens.append(f"Dia {dia.strftime('%d/%m/%Y')}: {qtd} {unidade} ausente(s).")

    return mensagens


def load_and_validate_csv(
    file_path: Union[str, Path],
    intervalo_horas: float = 1.0,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Carrega o arquivo CSV de medições, aplica validações técnicas e de engenharia,

    e retorna os dados válidos juntamente com um relatório detalhado.

    Contrato Técnico da Versão 1.0:
    - Cada timestamp deve representar o início exato de uma hora cheia (minuto, segundo e fração zero).
    - Não são aceitos fusos horários explícitos (UTC, offset +HH:MM ou sufixo Z); espera-se horário local.
    - Frações de segundo (microssegundos, nanossegundos) são estritamente rejeitadas para evitar perda de informação silenciosa.
    - A coluna 'potencia_kw' representa a potência média demandada na hora seguinte (kW).
    - Valores não finitos (NaN, Inf, -Inf) ou negativos são rejeitados.
    - Conflitos de medição (mesmo timestamp com potências diferentes) geram erro explícito imediato.
    - Duplicatas idênticas são tratadas de forma idempotente.
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

    # Validação de presença das colunas obrigatórias
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
        "linhas_descartadas": 0,
        "ausentes_descartados": 0,
        "data_invalida": 0,
        "fora_contrato_horario": 0,
        "potencia_nao_numerica_ou_infinita": 0,
        "negativos_rejeitados": 0,
        "duplicados_exatos_descartados": 0,
        "lacunas_detectadas": [],
        "avisos": [],
    }

    if total_lidos == 0:
        relatorio["avisos"].append("Arquivo contém apenas cabeçalhos sem linhas de dados.")
        return pd.DataFrame(columns=REQUIRED_COLUMNS), relatorio

    linhas_candidatas = []

    # Avaliação por linha com categorias mutuamente exclusivas
    for idx, row in df_raw.iterrows():
        raw_dt = row["data_hora"]
        raw_pot = row["potencia_kw"]

        # 1. Valores nulos ou vazios
        if pd.isna(raw_dt) or pd.isna(raw_pot) or str(raw_dt).strip() == "" or str(raw_pot).strip() == "":
            relatorio["ausentes_descartados"] += 1
            continue

        str_dt = str(raw_dt).strip()

        # 2. Contrato temporal: rejeitar fusos explícitos (UTC, GMT, offsets, Z) e frações de segundo
        tem_fuso_ou_fracao = bool(
            re.search(r"(?:[Zz]|UTC|GMT|(?:\+|\-)\d{2}(?::?\d{2})?)$|\.\d+", str_dt, re.IGNORECASE)
        )
        if tem_fuso_ou_fracao:
            relatorio["fora_contrato_horario"] += 1
            continue

        # 3. Validar sintaxe do timestamp local aceito (YYYY-MM-DD HH:MM ou YYYY-MM-DD HH:MM:SS)
        padrao_local = re.compile(
            r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])[ T](?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$"
        )
        if not padrao_local.match(str_dt):
            relatorio["data_invalida"] += 1
            continue

        # 4. Conversão da data/hora
        try:
            dt = pd.to_datetime(str_dt)
            if pd.isna(dt):
                relatorio["data_invalida"] += 1
                continue
        except Exception:
            relatorio["data_invalida"] += 1
            continue

        # 5. Conferir fuso e alinhamento com a grade do intervalo (segundo e frações zero)
        minutos_intervalo = int(round(intervalo_horas * 60))
        if minutos_intervalo <= 0:
            minutos_intervalo = 60

        if (
            dt.tzinfo is not None
            or dt.second != 0
            or dt.microsecond != 0
            or dt.nanosecond != 0
            or (dt.minute % minutos_intervalo != 0)
        ):
            relatorio["fora_contrato_horario"] += 1
            continue

        # 5. Conversão e finitude da potência elétrica
        try:
            pot_float = float(raw_pot)
            if not math.isfinite(pot_float):
                relatorio["potencia_nao_numerica_ou_infinita"] += 1
                continue
        except (ValueError, TypeError):
            relatorio["potencia_nao_numerica_ou_infinita"] += 1
            continue

        # 6. Potência não negativa (P >= 0)
        if pot_float < 0:
            relatorio["negativos_rejeitados"] += 1
            continue

        linhas_candidatas.append((dt, pot_float))

    if not linhas_candidatas:
        relatorio["linhas_descartadas"] = total_lidos
        relatorio["registros_validos"] = 0
        return pd.DataFrame(columns=REQUIRED_COLUMNS), relatorio

    df_cand = pd.DataFrame(linhas_candidatas, columns=["data_hora", "potencia_kw"])

    # 7. Detecção de conflitos no lote do CSV (mesmo timestamp com valores distintos de potência)
    agrup_conflitos = df_cand.groupby("data_hora")["potencia_kw"].nunique()
    conflitos = agrup_conflitos[agrup_conflitos > 1]
    if not conflitos.empty:
        exemplos_conflito = []
        for dt_conflito in conflitos.index[:3]:
            valores = df_cand[df_cand["data_hora"] == dt_conflito]["potencia_kw"].tolist()
            exemplos_conflito.append(f"{dt_conflito}: {valores} kW")
        raise ValueError(
            f"Conflito de dados no CSV: múltiplos registros com potências diferentes para o mesmo horário. "
            f"Exemplos: {'; '.join(exemplos_conflito)}"
        )

    # 8. Remover duplicatas idênticas (mesmo timestamp e exatamente o mesmo valor numérico)
    duplicados_mask = df_cand.duplicated(subset=["data_hora", "potencia_kw"], keep="first")
    qtd_duplicados = int(duplicados_mask.sum())
    if qtd_duplicados > 0:
        relatorio["duplicados_exatos_descartados"] = qtd_duplicados
        df_valid = df_cand[~duplicados_mask].copy()
    else:
        df_valid = df_cand.copy()

    df_valid = df_valid.sort_values("data_hora").reset_index(drop=True)

    # 9. Identificar lacunas temporais no lote importado
    lacunas = identificar_lacunas_temporais(df_valid, intervalo_horas=intervalo_horas)
    if lacunas:
        relatorio["lacunas_detectadas"] = [ts.strftime("%Y-%m-%d %H:%M") for ts in lacunas]
        resumo_lac = formatar_resumo_lacunas(lacunas, intervalo_horas=intervalo_horas)
        unidade = "hora(s)" if intervalo_horas == 1.0 else "medição(ões)"
        relatorio["avisos"].append(
            f"Detectada(s) {len(lacunas)} {unidade} ausente(s) no arquivo CSV entre "
            f"{df_valid['data_hora'].iloc[0].strftime('%d/%m/%Y %H:%M')} e "
            f"{df_valid['data_hora'].iloc[-1].strftime('%d/%m/%Y %H:%M')}. "
            f"{' '.join(resumo_lac)}"
        )

    relatorio["registros_validos"] = len(df_valid)
    # Calculado como soma das categorias para garantir consistência com os contadores individuais:
    # total_lidos == registros_validos + linhas_descartadas (identidade auditável)
    relatorio["linhas_descartadas"] = (
        relatorio["ausentes_descartados"]
        + relatorio["data_invalida"]
        + relatorio["fora_contrato_horario"]
        + relatorio["potencia_nao_numerica_ou_infinita"]
        + relatorio["negativos_rejeitados"]
        + relatorio["duplicados_exatos_descartados"]
    )

    if relatorio["ausentes_descartados"] > 0:
        relatorio["avisos"].append(f"{relatorio['ausentes_descartados']} linha(s) com campos nulos/vazios descartadas.")
    if relatorio["data_invalida"] > 0:
        relatorio["avisos"].append(f"{relatorio['data_invalida']} linha(s) com formato de data/hora inválido descartadas.")
    if relatorio["fora_contrato_horario"] > 0:
        relatorio["avisos"].append(
            f"{relatorio['fora_contrato_horario']} linha(s) fora do contrato horário (fuso explícito, frações de segundo ou minutos != 0) descartadas."
        )
    if relatorio["potencia_nao_numerica_ou_infinita"] > 0:
        relatorio["avisos"].append(
            f"{relatorio['potencia_nao_numerica_ou_infinita']} linha(s) com potência não numérica ou infinita descartadas."
        )
    if relatorio["negativos_rejeitados"] > 0:
        relatorio["avisos"].append(
            f"{relatorio['negativos_rejeitados']} linha(s) com potência negativa descartadas (fora do escopo de consumo)."
        )
    if relatorio["duplicados_exatos_descartados"] > 0:
        relatorio["avisos"].append(
            f"{relatorio['duplicados_exatos_descartados']} linha(s) duplicadas idênticas descartadas de forma idempotente."
        )

    return df_valid, relatorio
