"""Módulo de análise de dados e cálculo de indicadores de consumo e demanda.

Responsabilidades deste módulo:
- Realizar cálculos puros de Engenharia Elétrica sobre séries temporais:
  potência média, pico de demanda, integral de energia (kWh), fator de carga (FC),
  cobertura de medições e consolidação diária com participação percentual.
- Todas as funções deste módulo são FUNÇÕES PURAS: recebem dados (DataFrames ou números),
  não realizam operações de entrada/saída (I/O) em disco nem modificam dados externos,
  facilitando testes unitários determinísticos e reprodutíveis.

Conceitos de Programação e Engenharia de Software aplicados:
- 'TypedDict': Dicionários com contrato formal de tipos de chaves e valores.
  Permite ao Python e ao IDE checarem se nenhum campo obrigatório foi omitido.
- 'df.copy()': Cria uma cópia independente do DataFrame na memória RAM.
  Evita o efeito colateral ("side-effect") de modificar as colunas do chamador.
- 'groupby' e 'agg': Agrupamento relacional em memória com agregações vetorizadas
  compiladas em C (ordens de grandeza mais rápidas que laços 'for' manuais).
- 'sort_values': Ordenação determinística com desempate cronológico explícito.
- 'None': Utilizado para indicar que um indicador é "Não Aplicável" (ex: divisão por zero),
  distinguindo rigorosamente um valor nulo de um valor numérico zero.
"""

import math
from typing import Tuple, Optional, Dict, Any, TypedDict, Union
import pandas as pd


class CoberturaDict(TypedDict):
    """Estrutura tipada do resumo de cobertura temporal das medições.

    Campos:
        horas_medidas: Quantidade de intervalos com carimbos presentes no período.
        horas_esperadas: Quantidade total de passos temporais esperados entre a primeira
                         e a última medição registrada.
        horas_ausentes: Total de passos faltantes (horas_esperadas - horas_medidas).
        percentual_cobertura: Razão percentual (horas_medidas / horas_esperadas * 100).
                              None se não houver medições suficientes.
    """
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
    """Valida se o intervalo de tempo informado é finito e estritamente positivo (> 0).

    Por que validar precondições?
    - Na integral de energia (E = P * Δt) e na contagem de passos esperados (24 / Δt),
      um intervalo nulo (0), negativo ou infinito causaria erros graves de divisão por zero
      ou resultados sem sentido físico.
    """
    if not isinstance(intervalo_horas, (int, float)) or not math.isfinite(intervalo_horas) or intervalo_horas <= 0:
        raise ValueError(
            f"Intervalo de medição inválido: {intervalo_horas}. "
            f"Deve ser um número numérico finito e estritamente positivo (> 0)."
        )


def calcular_potencia_media(df: pd.DataFrame) -> float:
    """Calcula a potência ativa média registrada no período em kW.

    Conceito Elétrico:
    A potência média é a média aritmética das potências ativas amostradas:
        P_media = (1 / N) * Σ P_i
    Representa o nível contínuo de demanda equivalente que transferiria a mesma energia
    caso a carga fosse constante durante as N horas amostradas.

    Args:
        df: DataFrame contendo a coluna 'potencia_kw'.

    Returns:
        float: Potência média em kW (0.0 se DataFrame estiver vazio).

    Exemplo:
        >>> df = pd.DataFrame({"potencia_kw": [10.0, 20.0]})
        >>> calcular_potencia_media(df)
        15.0
    """
    if df.empty or "potencia_kw" not in df.columns:
        return 0.0
    return float(df["potencia_kw"].mean())


def calcular_demanda_maxima(df: pd.DataFrame) -> Tuple[float, Optional[str]]:
    """Identifica a maior demanda de potência registrada (kW) e o carimbo de tempo da ocorrência.

    Conceito Elétrico vs. Regulatório (REN ANEEL nº 1.000/2021):
    - No escopo didático deste projeto, o pico calculado é a maior potência média observada
      na resolução temporal dos dados (ex: média horária para amostragem de 1h).
    - Na regulação setorial (Art. 2º, XIII), 'demanda medida' é estritamente a maior demanda
      de potência ativa integralizada em intervalos de 15 minutos durante o período de faturamento.
      O pico aqui calculado identifica a ocorrência máxima da série analisada, sem constituir
      apurador de demanda faturável ou de ultrapassagem (Art. 301).

    Conceito de Programação: Ordenação e Desempate Determinístico ('sort_values')
    - Se houver dois picos iguais (ex: 20 kW às 09:00 e 20 kW às 18:00), qual deve ser exibido?
    - O método '.sort_values(["potencia_kw", "data_hora"], ascending=[False, True])':
      1. Ordena pela maior potência decrescente (False).
      2. Em caso de empate na potência, desempata pela menor data_hora crescente (True).
      Isso garante determinismo matemático: reexecuções sempre retornam a mesma ocorrência (a mais antiga).

    Por que usar 'df.copy()'?
    - Evita modificar o DataFrame original que foi passado por parâmetro pelo chamador.

    Args:
        df: DataFrame com colunas 'potencia_kw' e 'data_hora'.

    Returns:
        Tuple[float, Optional[str]]: (demanda_maxima_kw, "DD/MM/AAAA HH:MM").
        Se vazio, retorna (0.0, None).

    Exemplo:
        >>> df = pd.DataFrame({
        ...     "data_hora": pd.to_datetime(["2026-08-01 08:00", "2026-08-01 09:00"]),
        ...     "potencia_kw": [10.0, 20.0]
        ... })
        >>> calcular_demanda_maxima(df)
        (20.0, '01/08/2026 09:00')
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
    """Calcula a energia elétrica ativa total consumida no período em quilowatt-hora (kWh).

    Premissa e Análise Dimensional de Engenharia Elétrica:
    - Cada registro de potência representa a potência ativa média (kW) observada durante o intervalo amostral.
    - A energia elétrica ativa consumida (kWh) é a integral da potência ativa média no tempo:
          energia_kwh = potencia_media_kw * intervalo_horas
          E (kWh) = Σ (P_média [kW] * Δt [h])
    - Essa relação decorre estritamente da física de conservação de energia e conversão dimensional,
      não constituindo uma convenção regulatória ou tarifária.
    - Se Δt = 1.0h, o valor numérico da potência média na hora coincide com os kWh consumidos na hora.
    - Se Δt = 0.25h (15 min), uma potência média de 10 kW gera: 10 * 0.25 = 2.5 kWh.

    Args:
        df: DataFrame contendo a coluna 'potencia_kw'.
        intervalo_horas: Duração do intervalo em horas (ex: 1.0 ou 0.25).

    Returns:
        float: Energia acumulada em kWh (0.0 se vazio).

    Exemplo:
        >>> df = pd.DataFrame({"potencia_kw": [10.0, 20.0]})
        >>> calcular_consumo_total(df, intervalo_horas=1.0)
        30.0
    """
    validar_intervalo_horas(intervalo_horas)

    if df.empty or "potencia_kw" not in df.columns:
        return 0.0

    return float((df["potencia_kw"] * intervalo_horas).sum())


def calcular_consumo_diario(df: pd.DataFrame, intervalo_horas: float = 1.0) -> pd.DataFrame:
    """Agrupa medições horárias por data civil e calcula indicadores diários consolidados.

    Colunas Geradas no DataFrame Diário:
    - dia (str: YYYY-MM-DD): Data civil do calendário.
    - total_medicoes (int): Quantidade de medições presentes no dia.
    - dia_completo (bool): True se o dia possui a quantidade esperada de amostras em 24h
      (24 amostras para 1h; 96 amostras para 15min). Dias parciais recebem False.
    - potencia_media_kw (float): Média das potências das amostras presentes no dia.
    - demanda_maxima_kw (float): Maior potência registrada no dia.
    - consumo_kwh (float): Soma da energia dos intervalos registrados no dia.
    - participacao_percentual (float): Proporção (em %) do consumo do dia frente ao total do período.

    Conceito de Programação: 'groupby' e 'agg' no Pandas
    - 'df.groupby("dia")': Particiona as linhas do DataFrame em grupos baseados na data civil.
    - '.agg(...)': Aplica múltiplas agregações vetorizadas de uma só vez aos dados agrupados:
      'count' para contar amostras, 'mean' para potência média, 'max' para pico e 'sum' para energia.
    - Operações vetorizadas executam em código C pré-compilado, sendo extremamente eficientes.

    Significado de 'None' em 'participacao_percentual':
    - Se a energia total de todo o período for 0 kWh, calcular (0 / 0) geraria uma divisão por zero.
    - Nesses casos, o Pandas preenche com 'None' (Não Aplicável), garantindo robustez matemática.

    Args:
        df: DataFrame com colunas 'data_hora' e 'potencia_kw'.
        intervalo_horas: Passo amostral em horas (default: 1.0).

    Returns:
        pd.DataFrame: Tabela diária com as 7 colunas padronizadas.

    Exemplo:
        >>> df = pd.DataFrame({
        ...     "data_hora": pd.to_datetime(["2026-08-01 08:00", "2026-08-01 09:00"]),
        ...     "potencia_kw": [10.0, 20.0]
        ... })
        >>> res = calcular_consumo_diario(df, intervalo_horas=1.0)
        >>> len(res)
        1
        >>> float(res["consumo_kwh"].iloc[0])
        30.0
        >>> bool(res["dia_completo"].iloc[0])
        False
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
    """Calcula o Fator de Carga (FC) da instalação elétrica.

    Definição de Engenharia e Regulatória (REN ANEEL nº 1.000/2021, Art. 2º, XIX):
        FC = Potencia_Media / Demanda_Maxima = Demanda_Media / Demanda_Maxima
    - É a razão entre a demanda média e a demanda máxima da instalação no mesmo período de tempo.
    - É um valor adimensional entre 0.0 e 1.0 (ou 0% a 100%).
    - Dependência Metrológica: O valor do fator de carga depende estritamente da resolução
      amostral (Δt) e da cobertura temporal dos dados. Na presença de lacunas ou dados incompletos,
      sua interpretação fica estritamente restrita aos intervalos efetivamente medidos.

    Distinções Fundamentais de Engenharia:
    1. Fator de Carga vs. Fator de Potência: O fator de carga reflete modulação e uniformidade
       da curva de carga no tempo. NÃO deve ser confundido com o Fator de Potência (cos φ),
       que é a relação entre potência ativa (kW) e potência aparente (kVA), regulado no Art. 302
       da REN 1.000 com limite de referência indutivo/capacitivo de 0,92.
    2. Fator de Carga vs. Eficiência de Equipamentos: O FC mede o grau de utilização contínua
       da capacidade de demanda, e NÃO o rendimento de motores ou aparelhos. Um motor antigo
       operando 24h/dia terá FC = 1.0 (100%), enquanto um motor ultrarrentável ligado apenas 1h/dia
       terá FC baixo.

    Tratamento de Exceções e 'None':
    - Se a demanda máxima for nula (0.0 kW), negativa ou NaN, retorna 'None' ("Não Aplicável"),
      evitando divisões por zero ou valores sem sentido físico.

    Args:
        potencia_media_kw: Potência ativa média em kW.
        demanda_maxima_kw: Demanda de pico em kW.

    Returns:
        Optional[float]: Valor do fator de carga (0.0 a 1.0) ou None se não aplicável.

    Exemplo:
        >>> calcular_fator_carga(15.0, 20.0)
        0.75
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
    """Identifica a data civil com maior consumo de energia (kWh) e o status de completude do dia.

    Desempate Determinístico:
    - Ordena por 'consumo_kwh' decrescente (maior consumo primeiro).
    - Em caso de empate no consumo entre dois dias, desempata pela data civil crescente ('dia ASC').
    - Garante reproducibilidade total dos resultados.

    Args:
        df_diario: DataFrame retornado por 'calcular_consumo_diario'.

    Returns:
        Tuple[Optional[str], float, bool]:
            (dia_str, consumo_kwh, dia_completo).
            Se vazio, retorna (None, 0.0, False).

    Exemplo:
        >>> df_d = pd.DataFrame({"dia": ["2026-08-01"], "consumo_kwh": [30.0], "dia_completo": [False]})
        >>> identificar_dia_maior_consumo(df_d)
        ('2026-08-01', 30.0, False)
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
    """Calcula a integridade e cobertura temporal das medições no período delimitado.

    Como funciona o cálculo:
    1. 't_min' e 't_max': Primeiro e último carimbos cronológicos da série.
    2. 'passos_esperados': Quantidade teórica de intervalos que deveriam existir entre
       t_min e t_max: round(segundos_totais / intervalo_segundos) + 1.
    3. 'horas_medidas': Quantidade de carimbos distintos efetivamente presentes.
    4. 'horas_ausentes': max(0, passos_esperados - horas_medidas).
    5. 'percentual_cobertura': (horas_medidas / passos_esperados) * 100.

    DISTINÇÃO DIDÁTICA: Cobertura do Período vs. Dias Completos de 24h
    - Se recebermos medições das 08:00 e 09:00 (intervalo 1h):
      * Entre 08:00 e 09:00, esperamos 2 passos e temos 2 passos -> Cobertura do intervalo = 100,0%.
      * No entanto, o dia 01/08 possui apenas 2 de 24 horas -> O dia é parcial ('dia_completo == False').
      * Esta distinção técnica é vital para relatórios honestos e confiáveis.

    Args:
        df: DataFrame com coluna 'data_hora'.
        intervalo_horas: Duração de cada passo temporal em horas.

    Returns:
        CoberturaDict: Dicionário tipado com horas_medidas, horas_esperadas,
                       horas_ausentes e percentual_cobertura.
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
    """Calcula a estimativa simplificada de custo da energia elétrica ativa (R$).

    Fórmula: Custo (R$) = Consumo (kWh) * Tarifa (R$/kWh)

    Escopo Educacional vs. Faturamento Regulado:
    - Esta função calcula uma estimativa proporcional direta para fins didáticos e analíticos.
    - NÃO constitui fatura de energia nem substitui faturamento de concessionária (REN ANEEL nº 1.000/2021).
    - Não contempla componentes regulados de faturamento como: demanda faturável em R$/kW (Grupo A),
      custo de disponibilidade (Grupo B, Art. 290-291), faixas horárias da Tarifa Branca (Art. 212),
      adicionais de bandeiras tarifárias, tributos (ICMS, PIS, COFINS) ou cobrança por reativos excedentes (Art. 302).

    Precondições:
    - Consumo e tarifa devem ser números finitos não negativos (>= 0).
    - Valores NaN, Inf ou negativos disparam ValueError explicativo.

    Args:
        consumo_kwh: Energia total ativa em kWh.
        tarifa_kwh: Tarifa monômia configurada em R$/kWh.

    Returns:
        float: Custo estimado em Reais.

    Exemplo:
        >>> calcular_custo_estimado(30.0, 0.75)
        22.5
    """
    if not isinstance(consumo_kwh, (int, float)) or not math.isfinite(consumo_kwh) or consumo_kwh < 0:
        raise ValueError("Consumo (kWh) deve ser um número finito e não negativo (>= 0).")

    if not isinstance(tarifa_kwh, (int, float)) or not math.isfinite(tarifa_kwh) or tarifa_kwh < 0:
        raise ValueError("Tarifa (R$/kWh) deve ser um número finito e não negativo (>= 0).")

    return float(consumo_kwh * tarifa_kwh)


def gerar_indicadores_completos(
    df: pd.DataFrame, tarifa_kwh: float, intervalo_horas: float = 1.0
) -> IndicadoresCompletosDict:
    """Orquestra e consolida todos os indicadores técnicos em um contrato estruturado.

    Analogia com Engenharia Elétrica:
        Esta função atua como um painel consolidado de telemetria e análise de consumo.
        A partir da série temporal de potência ativa média integrada no intervalo,
        ela compila:
        1. Balanço energético (Consumo total em kWh e estimativa de custo simplificada em R$);
        2. Perfil de carregamento (Potência média e Demanda máxima de pico);
        3. Fator de carga da instalação (uniformidade do uso da potência em relação ao pico registrado, Art. 2º, XIX);
        4. Agregação diária e dia crítico (maior consumo acumulado);
        5. Confiabilidade metrológica (cobertura temporal e horas ausentes).

    Conceito de Programação:
        - Orquestração de Funções Puras: Reúne funções especializadas e testadas
          isoladamente, garantindo modularidade e manutenibilidade.
        - Performance & Caching: Retorna o 'df_diario' calculado internamente
          diretamente no dicionário tipado 'IndicadoresCompletosDict', evitando que o
          pipeline principal ('main.py') processe novamente o agrupamento 'groupby'.
        - Contrato Rígido de Saída: O retorno é aderente ao 'IndicadoresCompletosDict',
          garantindo previsibilidade para módulos consumidores (relatórios CLI, CSV).

    Args:
        df: DataFrame contendo as colunas 'data_hora' e 'potencia_kw'.
        tarifa_kwh: Tarifa monômia em R$/kWh.
        intervalo_horas: Passo temporal das medições em horas (default 1.0h).

    Returns:
        IndicadoresCompletosDict contendo todos os indicadores calculados e o DataFrame diário.
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
    """Gera uma síntese executiva textual interpretando os indicadores para engenharia e gestão.

    Analogia com Engenharia Elétrica & Gestão de Energia:
        Um engenheiro não entrega apenas números brutos a um gerente ou cliente; ele fornece
        diagnóstico técnico fundamentado em dados:
        1. Contexto Metrológico: Quantifica medições reais e ressalta lacunas temporais,
           alertando que médias e fatores de carga refletem estritamente os intervalos medidos;
        2. Carregamento e Concentração: Destaca o instante da demanda de ponta e a concentração
           de consumo diário (% da energia total registrada no período);
        3. Fator de Carga Desmistificado: Explica tecnicamente que o FC mede modulação da curva
           de carga e taxa de utilização da infraestrutura elétrica, e NÃO eficiência dos motores/cargas;
        4. Recomendações Prudentes: Sugere investigação operacional de campo (curvas de carga,
           partida simultânea de motores) sem especular defeitos ou prescrever alterações cegas.

    Regras de Negócio e Confiabilidade:
        - 100% Determinística: Saída gerada unicamente a partir dos parâmetros fornecidos.
        - Não Extrapolação: Nunca inventa valores para períodos faltantes.
        - Tratamento de Dados Nulos: Se a série for vazia, retorna aviso claro em vez de erro.

    Args:
        indicadores: Dicionário contendo os indicadores calculados por 'gerar_indicadores_completos'.
        df_diario: DataFrame com a agregação diária de consumo.
        tem_lacunas: Flag booleano indicando presença de lacunas detectadas na importação.

    Returns:
        Texto formatado em 4 parágrafos executivos com formatação numérica brasileira.
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
