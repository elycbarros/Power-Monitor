"""Testes unitários, de regressão e de integração para o PowerMonitor."""

import math
import re
import pytest
import pandas as pd
from pathlib import Path

from src.analysis import (
    calcular_potencia_media,
    calcular_demanda_maxima,
    calcular_consumo_total,
    calcular_consumo_diario,
    calcular_custo_estimado,
    gerar_indicadores_completos,
    calcular_fator_carga,
    identificar_dia_maior_consumo,
    calcular_cobertura_medicoes,
    gerar_sintese_executiva,
)
from src.import_data import load_and_validate_csv, identificar_lacunas_temporais, formatar_resumo_lacunas
from src.database import get_connection, create_tables, insert_medicoes, query_to_dataframe


@pytest.fixture
def dados_exemplo():
    """Fixture com medições controladas para testes."""
    return pd.DataFrame(
        {
            "data_hora": pd.to_datetime(
                [
                    "2026-08-01 08:00:00",
                    "2026-08-01 09:00:00",
                    "2026-08-01 10:00:00",
                    "2026-08-01 11:00:00",
                ]
            ),
            "potencia_kw": [10.0, 20.0, 30.0, 20.0],
        }
    )


# ----------------------------------------------------------------------
# 1. Cálculos de Engenharia Elétrica (Pandas)
# ----------------------------------------------------------------------


def test_calculo_potencia_media(dados_exemplo):
    """Verifica se a média de potência (kW) é calculada corretamente."""
    media = calcular_potencia_media(dados_exemplo)
    assert media == 20.0


def test_calculo_demanda_maxima(dados_exemplo):
    """Verifica identificação da maior demanda e do horário correspondente."""
    demanda_max, horario = calcular_demanda_maxima(dados_exemplo)
    assert demanda_max == 30.0
    assert "01/08/2026 10:00" in horario


def test_calculo_demanda_maxima_desempate_deterministico():
    """Em caso de empate na potência máxima, seleciona a ocorrência cronologicamente anterior."""
    df_empate = pd.DataFrame(
        {
            "data_hora": pd.to_datetime(["2026-08-01 14:00:00", "2026-08-01 10:00:00", "2026-08-01 18:00:00"]),
            "potencia_kw": [25.0, 25.0, 20.0],
        }
    )
    demanda_max, horario = calcular_demanda_maxima(df_empate)
    assert demanda_max == 25.0
    assert "01/08/2026 10:00" in horario


def test_calculo_consumo_total(dados_exemplo):
    """Verifica se a energia em kWh considera o intervalo regular em horas.

    Energia = Σ (P * Δt)
    """
    consumo = calcular_consumo_total(dados_exemplo, intervalo_horas=1.0)
    assert consumo == 80.0

    consumo_meia_hora = calcular_consumo_total(dados_exemplo, intervalo_horas=0.5)
    assert consumo_meia_hora == 40.0


def test_calculo_custo_estimado():
    """Verifica se o custo financeiro é proporcional ao consumo e à tarifa."""
    custo = calcular_custo_estimado(consumo_kwh=100.0, tarifa_kwh=0.75)
    assert custo == 75.0


def test_validacao_intervalo_horas():
    """Garante rejeição de intervalos nulos, negativos ou não finitos."""
    df = pd.DataFrame({"potencia_kw": [10.0]})
    with pytest.raises(ValueError):
        calcular_consumo_total(df, intervalo_horas=0.0)

    with pytest.raises(ValueError):
        calcular_consumo_total(df, intervalo_horas=-1.0)

    with pytest.raises(ValueError):
        calcular_consumo_total(df, intervalo_horas=float("inf"))

    with pytest.raises(ValueError):
        calcular_consumo_total(df, intervalo_horas=float("nan"))


def test_validacao_custo_estimado_valores_invalidos():
    """Garante que tarifas ou consumos negativos/não finitos levantam exceção."""
    with pytest.raises(ValueError):
        calcular_custo_estimado(consumo_kwh=-10.0, tarifa_kwh=0.75)

    with pytest.raises(ValueError):
        calcular_custo_estimado(consumo_kwh=50.0, tarifa_kwh=-0.50)

    with pytest.raises(ValueError):
        calcular_custo_estimado(consumo_kwh=float("nan"), tarifa_kwh=0.75)

    with pytest.raises(ValueError):
        calcular_custo_estimado(consumo_kwh=50.0, tarifa_kwh=float("inf"))


def test_calculo_consumo_diario():
    """Testa agrupamento diário e detecção de dias completos vs parciais proporcionalmente ao intervalo."""
    # 24 medições horárias = 1 dia completo para intervalo_horas = 1.0
    datas_completas = pd.date_range("2026-08-01 00:00", "2026-08-01 23:00", freq="1h")
    df_completo = pd.DataFrame({"data_hora": datas_completas, "potencia_kw": [10.0] * 24})

    diario_1h = calcular_consumo_diario(df_completo, intervalo_horas=1.0)
    assert diario_1h["dia_completo"].iloc[0] is True or diario_1h["dia_completo"].iloc[0] == 1
    assert diario_1h["consumo_kwh"].iloc[0] == 240.0

    # Com intervalo de 0.5h, 24 medições correspondem a apenas 12h, logo o dia NÃO é completo
    diario_meia_hora = calcular_consumo_diario(df_completo, intervalo_horas=0.5)
    assert diario_meia_hora["dia_completo"].iloc[0] is False or diario_meia_hora["dia_completo"].iloc[0] == 0


def test_fator_carga_cenarios():
    """Verifica o cálculo do fator de carga para carga constante, variável e potência zero."""
    # 1. Carga constante: FC = 1.0 (100%)
    fc_const = calcular_fator_carga(potencia_media_kw=20.0, demanda_maxima_kw=20.0)
    assert fc_const == 1.0

    # 2. Carga variável: FC = 20.0 / 30.0 (~0.6667)
    fc_var = calcular_fator_carga(potencia_media_kw=20.0, demanda_maxima_kw=30.0)
    assert fc_var is not None
    assert math.isclose(fc_var, 20.0 / 30.0, abs_tol=0.0001)

    # 3. Potência zero: Demanda máxima nula -> None (não aplicável, sem ZeroDivisionError)
    fc_zero = calcular_fator_carga(potencia_media_kw=0.0, demanda_maxima_kw=0.0)
    assert fc_zero is None

    # 4. Valores negativos ou inválidos -> None
    assert calcular_fator_carga(potencia_media_kw=10.0, demanda_maxima_kw=-5.0) is None
    assert calcular_fator_carga(potencia_media_kw=10.0, demanda_maxima_kw=float("nan")) is None


def test_cobertura_medicoes_cenarios():
    """Verifica o cálculo de cobertura para série completa, lacunas, medição única e bordas parciais."""
    # 1. Série completa de 24 horas (01/08 00:00 a 23:00)
    df_24h = pd.DataFrame({"data_hora": pd.date_range("2026-08-01 00:00", "2026-08-01 23:00", freq="1h")})
    cob_24h = calcular_cobertura_medicoes(df_24h, intervalo_horas=1.0)
    assert cob_24h["horas_medidas"] == 24
    assert cob_24h["horas_esperadas"] == 24
    assert cob_24h["horas_ausentes"] == 0
    assert cob_24h["percentual_cobertura"] == 100.0

    # 2. Com lacuna: 08:00, 09:00 e 11:00 (10:00 ausente) -> 4 horas esperadas, 1 ausente (75%)
    df_lacuna = pd.DataFrame({"data_hora": pd.to_datetime(["2026-08-01 08:00", "2026-08-01 09:00", "2026-08-01 11:00"])})
    cob_lacuna = calcular_cobertura_medicoes(df_lacuna, intervalo_horas=1.0)
    assert cob_lacuna["horas_medidas"] == 3
    assert cob_lacuna["horas_esperadas"] == 4
    assert cob_lacuna["horas_ausentes"] == 1
    assert cob_lacuna["percentual_cobertura"] == 75.0

    # 3. Uma única medição -> 1 hora esperada, 1 medida, 0 ausentes, 100% de cobertura
    df_unica = pd.DataFrame({"data_hora": pd.to_datetime(["2026-08-01 08:00"])})
    cob_unica = calcular_cobertura_medicoes(df_unica, intervalo_horas=1.0)
    assert cob_unica["horas_medidas"] == 1
    assert cob_unica["horas_esperadas"] == 1
    assert cob_unica["horas_ausentes"] == 0
    assert cob_unica["percentual_cobertura"] == 100.0

    # 4. Dias de borda parciais: 01/08 das 14:00 às 23:00 (10h) e 02/08 das 00:00 às 10:00 (11h)
    # Total de 21 horas contínuas monitoradas -> Cobertura 100% no período, mas ambos são dias parciais
    datas_bordas = pd.date_range("2026-08-01 14:00", "2026-08-02 10:00", freq="1h")
    df_bordas = pd.DataFrame({"data_hora": datas_bordas, "potencia_kw": [10.0] * len(datas_bordas)})
    cob_bordas = calcular_cobertura_medicoes(df_bordas, intervalo_horas=1.0)
    assert cob_bordas["horas_medidas"] == 21
    assert cob_bordas["horas_esperadas"] == 21
    assert cob_bordas["horas_ausentes"] == 0
    assert cob_bordas["percentual_cobertura"] == 100.0

    diario_bordas = calcular_consumo_diario(df_bordas, intervalo_horas=1.0)
    assert (diario_bordas["dia_completo"] == False).all()

    # 5. DataFrame vazio
    cob_vazio = calcular_cobertura_medicoes(pd.DataFrame(), intervalo_horas=1.0)
    assert cob_vazio["horas_medidas"] == 0
    assert cob_vazio["horas_esperadas"] == 0
    assert cob_vazio["percentual_cobertura"] is None


def test_participacao_diaria_e_energia_zero():
    """Verifica o cálculo da fração percentual diária do consumo e tratamento de energia zero."""
    # 1. Dois dias normais: Dia 1 = 100 kWh, Dia 2 = 300 kWh (Total = 400 kWh)
    df_normal = pd.DataFrame(
        {
            "data_hora": pd.to_datetime(["2026-08-01 08:00", "2026-08-02 08:00"]),
            "potencia_kw": [100.0, 300.0],
        }
    )
    res_normal = calcular_consumo_diario(df_normal, intervalo_horas=1.0)
    assert res_normal["participacao_percentual"].iloc[0] == 25.0
    assert res_normal["participacao_percentual"].iloc[1] == 75.0

    # 2. Energia total zero: potências 0.0 -> participacao_percentual deve ser None (sem divisão por zero)
    df_zero = pd.DataFrame(
        {
            "data_hora": pd.to_datetime(["2026-08-01 08:00", "2026-08-02 08:00"]),
            "potencia_kw": [0.0, 0.0],
        }
    )
    res_zero = calcular_consumo_diario(df_zero, intervalo_horas=1.0)
    assert res_zero["participacao_percentual"].iloc[0] is None
    assert res_zero["participacao_percentual"].iloc[1] is None


def test_desempate_dia_maior_consumo():
    """Em caso de empate no consumo de dias distintos, seleciona deterministicamente a data mais antiga."""
    df_empate = pd.DataFrame(
        {
            "dia": ["2026-08-03", "2026-08-01", "2026-08-02"],
            "consumo_kwh": [350.0, 350.0, 200.0],
            "dia_completo": [True, True, True],
        }
    )
    dia, consumo, completo = identificar_dia_maior_consumo(df_empate)
    assert dia == "2026-08-01"
    assert consumo == 350.0
    assert completo is True


def test_sintese_executiva_dados_incompletos():
    """Verifica que a síntese executiva gera texto coerente com dias parciais e lacunas,
    sem divisão por zero e mantendo premissas técnicas responsáveis.
    """
    # DataFrame parcial com lacuna
    df_teste = pd.DataFrame(
        {
            "data_hora": pd.to_datetime(["2026-08-01 10:00", "2026-08-01 12:00"]),  # 11:00 ausente
            "potencia_kw": [15.0, 25.0],
        }
    )
    indicadores = gerar_indicadores_completos(df_teste, tarifa_kwh=0.75, intervalo_horas=1.0)
    df_diario = calcular_consumo_diario(df_teste, intervalo_horas=1.0)

    sintese = gerar_sintese_executiva(indicadores, df_diario, tem_lacunas=True)

    assert "25,00 kW" in sintese
    assert "01/08/2026" in sintese
    assert "fator de carga" in sintese.lower()
    assert "sem qualquer preenchimento artificial" in sintese
    assert "cobertura parcial" in sintese
    assert "sem inferir desperdício" in sintese or "sem presumir desperdício" in sintese


# ----------------------------------------------------------------------
# 2. Validação e Contrato de Dados (import_data)
# ----------------------------------------------------------------------


def test_rejeicao_potencia_negativa(tmp_path):
    """Garante que medições com potência negativa são rejeitadas pela validação."""
    csv_content = (
        "data_hora,potencia_kw\n"
        "2026-08-01 08:00,15.0\n"
        "2026-08-01 09:00,-5.0\n"
        "2026-08-01 10:00,12.5\n"
    )
    temp_csv = tmp_path / "teste_negativo.csv"
    temp_csv.write_text(csv_content, encoding="utf-8")

    df_valid, relatorio = load_and_validate_csv(temp_csv)
    assert relatorio["negativos_rejeitados"] == 1
    assert len(df_valid) == 2
    assert (df_valid["potencia_kw"] >= 0).all()


def test_rejeicao_potencia_infinita(tmp_path):
    """Garante que valores infinitos (inf, -inf) em potencia_kw são rejeitados."""
    csv_content = (
        "data_hora,potencia_kw\n"
        "2026-08-01 08:00,15.0\n"
        "2026-08-01 09:00,inf\n"
        "2026-08-01 10:00,-inf\n"
        "2026-08-01 11:00,18.0\n"
    )
    temp_csv = tmp_path / "teste_inf.csv"
    temp_csv.write_text(csv_content, encoding="utf-8")

    df_valid, relatorio = load_and_validate_csv(temp_csv)
    assert relatorio["potencia_nao_numerica_ou_infinita"] == 2
    assert len(df_valid) == 2


def test_estatisticas_validacao_mutuamente_exclusivas(tmp_path):
    """Garante que a contagem de linhas é estrita e mutuamente exclusiva,

    evitando contar a mesma linha duas vezes quando data e potência são inválidas,
    e comprovando a identidade contábil:
    total_lidos == registros_validos + linhas_descartadas, onde
    linhas_descartadas == soma exata de todas as categorias individuais de descarte.
    """
    csv_content = (
        "data_hora,potencia_kw\n"
        "2026-08-01 08:00,10.0\n"         # Válida (1)
        "data_invalida,invalida\n"        # Data inválida (1)
        "2026-08-01 10:00,\n"             # Ausente/nulo (1)
        "2026-08-01 11:00,15.0\n"         # Válida (2)
        "2026-08-01 11:00,15.0\n"         # Duplicada idêntica (1)
        "2026-08-01 12:00,-5.0\n"         # Negativo (1)
        "2026-08-01 13:00,inf\n"          # Potência infinita/não numérica (1)
        "2026-08-01 14:15,20.0\n"         # Fora de contrato horário (1)
    )
    temp_csv = tmp_path / "teste_estatisticas.csv"
    temp_csv.write_text(csv_content, encoding="utf-8")

    df_valid, relatorio = load_and_validate_csv(temp_csv)

    # Verificação das categorias individuais
    assert relatorio["ausentes_descartados"] == 1
    assert relatorio["data_invalida"] == 1
    assert relatorio["fora_contrato_horario"] == 1
    assert relatorio["potencia_nao_numerica_ou_infinita"] == 1
    assert relatorio["negativos_rejeitados"] == 1
    assert relatorio["duplicados_exatos_descartados"] == 1

    soma_categorias = (
        relatorio["ausentes_descartados"]
        + relatorio["data_invalida"]
        + relatorio["fora_contrato_horario"]
        + relatorio["potencia_nao_numerica_ou_infinita"]
        + relatorio["negativos_rejeitados"]
        + relatorio["duplicados_exatos_descartados"]
    )

    # Identidades contábeis auditáveis
    assert relatorio["total_lidos"] == 8
    assert relatorio["registros_validos"] == 2
    assert relatorio["linhas_descartadas"] == 6
    assert relatorio["linhas_descartadas"] == soma_categorias
    assert relatorio["total_lidos"] == relatorio["registros_validos"] + relatorio["linhas_descartadas"]
    assert len(df_valid) == relatorio["registros_validos"]


def test_contrato_temporal_minutos_fracionados(tmp_path):
    """Garante que medições sub-horárias (ex: 08:30) são rejeitadas pelo contrato da v1."""
    csv_content = (
        "data_hora,potencia_kw\n"
        "2026-08-01 08:00,10.0\n"
        "2026-08-01 08:30,12.5\n"   # Viola contrato horário
        "2026-08-01 09:00,14.0\n"
    )
    temp_csv = tmp_path / "teste_contrato.csv"
    temp_csv.write_text(csv_content, encoding="utf-8")

    df_valid, relatorio = load_and_validate_csv(temp_csv)
    assert relatorio["fora_contrato_horario"] == 1
    assert len(df_valid) == 2


def test_rejeicao_timestamps_com_fuso_ou_fracoes_segundo(tmp_path):
    """Garante rejeição de carimbos com fuso explícito (UTC, GMT, offsets, Z) ou frações de segundo."""
    csv_content = (
        "data_hora,potencia_kw\n"
        "2026-08-01 08:00 UTC,10.0\n"                 # Fuso UTC explícito
        "2026-08-01 08:00 GMT,11.0\n"                 # Fuso GMT explícito
        "2026-08-01 08:00:00+03:00,12.0\n"           # Offset positivo
        "2026-08-01 08:00:00-03:00,13.0\n"           # Offset negativo
        "2026-08-01 08:00:00Z,14.0\n"                # Sufixo Z
        "2026-08-01 08:00:00.000000001,15.0\n"       # Nanossegundos
        "2026-08-01 08:00,20.0\n"                    # Válido no contrato v1
    )
    temp_csv = tmp_path / "teste_fuso_completo.csv"
    temp_csv.write_text(csv_content, encoding="utf-8")

    df_valid, relatorio = load_and_validate_csv(temp_csv)
    # 6 entradas rejeitadas por violarem o contrato horário/local estrito
    assert relatorio["fora_contrato_horario"] == 6
    assert len(df_valid) == 1
    assert df_valid["potencia_kw"].iloc[0] == 20.0


def test_deteccao_lacunas_temporais_no_csv(tmp_path):
    """Garante que horas faltantes na série do CSV são identificadas e reportadas."""
    csv_content = (
        "data_hora,potencia_kw\n"
        "2026-08-01 08:00,10.0\n"
        "2026-08-01 09:00,12.0\n"
        # 10:00 ausente
        "2026-08-01 11:00,15.0\n"
    )
    temp_csv = tmp_path / "teste_lacuna.csv"
    temp_csv.write_text(csv_content, encoding="utf-8")

    df_valid, relatorio = load_and_validate_csv(temp_csv)
    assert len(relatorio["lacunas_detectadas"]) == 1
    assert "2026-08-01 10:00" in relatorio["lacunas_detectadas"][0]


def test_conflito_potencia_mesmo_horario_no_csv(tmp_path):
    """Garante que timestamps idênticos com potências divergentes disparam erro explícito no CSV."""
    csv_content = (
        "data_hora,potencia_kw\n"
        "2026-08-01 08:00,10.0\n"
        "2026-08-01 08:00,20.0\n"   # Conflito para o mesmo horário
    )
    temp_csv = tmp_path / "teste_conflito.csv"
    temp_csv.write_text(csv_content, encoding="utf-8")

    with pytest.raises(ValueError, match="Conflito de dados no CSV"):
        load_and_validate_csv(temp_csv)


# ----------------------------------------------------------------------
# 3. Banco de Dados, Idempotência e Atomicidade (SQLite)
# ----------------------------------------------------------------------


def test_reexecucao_idempotente(tmp_path):
    """Reimportar medições idênticas deve ser idempotente (retornar 0 novas)."""
    db_path = tmp_path / "test_idem.db"
    conn = get_connection(db_path)
    create_tables(conn)

    df = pd.DataFrame(
        {
            "data_hora": pd.to_datetime(["2026-08-01 08:00:00", "2026-08-01 09:00:00"]),
            "potencia_kw": [12.5, 18.0],
        }
    )

    inseridos_1 = insert_medicoes(conn, df)
    assert inseridos_1 == 2

    inseridos_2 = insert_medicoes(conn, df)
    assert inseridos_2 == 0

    df_res = query_to_dataframe(conn, "SELECT * FROM medicoes")
    assert len(df_res) == 2
    conn.close()


def test_reversao_lote_conflitante_sqlite(tmp_path):
    """Se um lote tentar inserir um timestamp com potência conflitante,

    deve lançar ValueError e reverter 100% do lote (nenhuma linha do novo lote inserida).
    """
    db_path = tmp_path / "test_conflito.db"
    conn = get_connection(db_path)
    create_tables(conn)

    # 1. Inserir lote inicial
    df_inicial = pd.DataFrame(
        {
            "data_hora": pd.to_datetime(["2026-08-01 08:00:00", "2026-08-01 09:00:00"]),
            "potencia_kw": [10.0, 15.0],
        }
    )
    assert insert_medicoes(conn, df_inicial) == 2

    # 2. Tentar inserir lote conflitante
    df_conflitante = pd.DataFrame(
        {
            "data_hora": pd.to_datetime(["2026-08-01 10:00:00", "2026-08-01 08:00:00"]),
            "potencia_kw": [30.0, 25.0],
        }
    )

    with pytest.raises(ValueError, match="Conflito de integridade"):
        insert_medicoes(conn, df_conflitante)

    # 3. Verificar que o banco continua exatamente com as 2 linhas originais (10:00 NÃO foi inserida)
    df_pos = query_to_dataframe(conn, "SELECT * FROM medicoes")
    assert len(df_pos) == 2
    assert set(df_pos["potencia_kw"]) == {10.0, 15.0}
    conn.close()


def test_conflito_potencia_pequena_diferenca_sqlite(tmp_path):
    """Garante que mesmo diferenças pequenas (ex: 10.00005 vs 10.0) geram erro e rollback,

    evitando mascarar alterações sutis de telemetria.
    """
    db_path = tmp_path / "test_pequeno_conflito.db"
    conn = get_connection(db_path)
    create_tables(conn)

    df_base = pd.DataFrame({"data_hora": ["2026-08-01 08:00:00"], "potencia_kw": [10.0]})
    insert_medicoes(conn, df_base)

    df_dif_pequena = pd.DataFrame({"data_hora": ["2026-08-01 08:00:00"], "potencia_kw": [10.00005]})
    with pytest.raises(ValueError, match="Conflito de integridade"):
        insert_medicoes(conn, df_dif_pequena)

    conn.close()


def test_deteccao_lacunas_no_historico_multiplas_importacoes(tmp_path):
    """Verifica detecção de lacunas no histórico consolidado do SQLite

    quando dois lotes contínuos são importados com dias de intervalo entre si.
    """
    db_path = tmp_path / "test_hist_lacuna.db"
    conn = get_connection(db_path)
    create_tables(conn)

    # Lote 1: 01/08 completo (24 horas)
    lote1 = pd.DataFrame(
        {
            "data_hora": pd.date_range("2026-08-01 00:00", "2026-08-01 23:00", freq="1h"),
            "potencia_kw": [10.0] * 24,
        }
    )
    insert_medicoes(conn, lote1)

    # Lote 2: 03/08 completo (24 horas) - O dia 02/08 está 100% ausente no histórico
    lote2 = pd.DataFrame(
        {
            "data_hora": pd.date_range("2026-08-03 00:00", "2026-08-03 23:00", freq="1h"),
            "potencia_kw": [15.0] * 24,
        }
    )
    insert_medicoes(conn, lote2)

    df_historico = query_to_dataframe(conn, "SELECT data_hora, potencia_kw FROM medicoes ORDER BY data_hora ASC")
    lacunas = identificar_lacunas_temporais(df_historico)

    # Devem existir exatamente 24 horas ausentes (todo o dia 02/08)
    assert len(lacunas) == 24
    resumo = formatar_resumo_lacunas(lacunas)
    assert any("02/08/2026" in r for r in resumo)

    conn.close()


# ----------------------------------------------------------------------
# 4. Concordância Matemática Carregando sql/queries.sql Diretamente
# ----------------------------------------------------------------------


def test_concordancia_sql_e_pandas_usando_arquivo_queries(tmp_path):
    """Garante que as consultas do arquivo sql/queries.sql produzem resultados

    matematicamente equivalentes aos cálculos do Pandas sobre o mesmo histórico,
    alinhando os dados por data civil e verificando o timestamp do pico.
    """
    db_path = tmp_path / "test_sql_file.db"
    conn = get_connection(db_path)
    create_tables(conn)

    # 48 horas de dados com variação controlada
    df_test = pd.DataFrame(
        {
            "data_hora": pd.date_range("2026-08-01 00:00", "2026-08-02 23:00", freq="1h"),
            "potencia_kw": [10.0 + (i % 15) for i in range(48)],
        }
    )
    insert_medicoes(conn, df_test)

    # Carregar o arquivo sql/queries.sql real do projeto
    sql_file = Path(__file__).resolve().parent.parent / "sql" / "queries.sql"
    assert sql_file.exists(), f"Arquivo não encontrado: {sql_file}"
    conteudo_sql = sql_file.read_text(encoding="utf-8")

    # Limpar comentários antes de separar por ';'
    linhas_validas = [l for l in conteudo_sql.splitlines() if not l.strip().startswith("--")]
    sql_limpo = "\n".join(linhas_validas)
    consultas = [q.strip() for q in sql_limpo.split(";") if q.strip()]

    # 1. Consulta 1: Potência Média Geral
    query_media = [c for c in consultas if "AVG(potencia_kw)" in c and "GROUP BY" not in c and "consumo_total_kwh" not in c][0]
    df_res_media = query_to_dataframe(conn, query_media)
    media_sql = float(df_res_media.iloc[0, 0])
    media_pd = round(calcular_potencia_media(df_test), 2)
    assert math.isclose(media_sql, media_pd, abs_tol=0.01)

    # 2. Consulta 2: Demanda Máxima e Horário do Pico
    query_demanda = [c for c in consultas if "ORDER BY potencia_kw DESC" in c][0]
    df_res_demanda = query_to_dataframe(conn, query_demanda)
    demanda_max_sql = float(df_res_demanda["demanda_maxima_kw"].iloc[0])
    dt_pico_sql = str(pd.to_datetime(df_res_demanda["data_hora"].iloc[0]))[:16]

    demanda_max_pd, horario_pd = calcular_demanda_maxima(df_test)
    dt_pico_pd = pd.to_datetime(horario_pd, format="%d/%m/%Y %H:%M").strftime("%Y-%m-%d %H:%M")

    assert math.isclose(demanda_max_sql, demanda_max_pd, abs_tol=0.01)
    assert dt_pico_sql == dt_pico_pd

    # 3. Consulta 3: Análise Diária Alinhada por Data
    query_diaria = [c for c in consultas if "GROUP BY DATE(data_hora)" in c and "LIMIT" not in c][0]
    df_res_diaria = query_to_dataframe(conn, query_diaria)
    df_diaria_pd = calcular_consumo_diario(df_test, intervalo_horas=1.0)

    # Merge explícito por dia para garantir alinhamento exato das datas
    merged = pd.merge(df_res_diaria, df_diaria_pd, on="dia", suffixes=("_sql", "_pd"))
    assert len(merged) == len(df_diaria_pd)

    for _, row in merged.iterrows():
        assert row["total_medicoes_sql"] == row["total_medicoes_pd"]
        assert math.isclose(float(row["potencia_media_kw_sql"]), float(row["potencia_media_kw_pd"]), abs_tol=0.01)
        assert math.isclose(float(row["demanda_maxima_kw_sql"]), float(row["demanda_maxima_kw_pd"]), abs_tol=0.01)
        assert math.isclose(float(row["consumo_estimado_kwh"]), float(row["consumo_kwh"]), abs_tol=0.01)
        if "participacao_percentual_sql" in row and row["participacao_percentual_sql"] is not None:
            assert math.isclose(
                float(row["participacao_percentual_sql"]), float(row["participacao_percentual_pd"]), abs_tol=0.01
            )

    # 4. Consulta 4: Resumo Geral Consolidado
    query_resumo = [c for c in consultas if "consumo_total_kwh" in c and "GROUP BY" not in c][0]
    df_res_resumo = query_to_dataframe(conn, query_resumo)
    consumo_tot_sql = float(df_res_resumo["consumo_total_kwh"].iloc[0])
    consumo_tot_pd = round(calcular_consumo_total(df_test, intervalo_horas=1.0), 2)
    assert math.isclose(consumo_tot_sql, consumo_tot_pd, abs_tol=0.01)
    if "fator_carga_percentual" in df_res_resumo.columns:
        fc_sql = float(df_res_resumo["fator_carga_percentual"].iloc[0])
        fc_pd = round(calcular_fator_carga(media_pd, demanda_max_pd) * 100.0, 2)
        assert math.isclose(fc_sql, fc_pd, abs_tol=0.05)

    # 5. Consulta 5: Dia de Maior Consumo
    query_dia_max = [c for c in consultas if "consumo_diario_kwh" in c and "LIMIT 1" in c][0]
    df_res_dia_max = query_to_dataframe(conn, query_dia_max)
    dia_sql = str(df_res_dia_max["dia"].iloc[0])
    consumo_dia_sql = float(df_res_dia_max["consumo_diario_kwh"].iloc[0])

    dia_pd, consumo_dia_pd, _ = identificar_dia_maior_consumo(df_diaria_pd)
    assert dia_sql == dia_pd
    assert math.isclose(consumo_dia_sql, consumo_dia_pd, abs_tol=0.01)

    conn.close()


# ----------------------------------------------------------------------
# 5. Testes Ponta a Ponta do Pipeline e Códigos de Saída
# ----------------------------------------------------------------------


def test_pipeline_configuracao_incompativel_antes_da_persistencia(tmp_path, monkeypatch):
    """Garante que configurações incompatíveis (INTERVALO_HORAS != 1.0 ou tarifa < 0)

    interrompem o pipeline antes de criar tabelas ou persistir medições no banco.
    """
    import main
    import config

    temp_csv = tmp_path / "medicoes.csv"
    temp_db = tmp_path / "nao_deve_existir.db"
    temp_out = tmp_path / "relatorio.csv"

    temp_csv.write_text("data_hora,potencia_kw\n2026-08-01 08:00,10.0\n", encoding="utf-8")

    monkeypatch.setattr(config, "CSV_PATH", temp_csv)
    monkeypatch.setattr(config, "DATABASE_PATH", temp_db)
    monkeypatch.setattr(config, "OUTPUT_PATH", temp_out)

    # 1. INTERVALO_HORAS não suportado (ex: 0.33h) deve falhar antes de criar o banco
    monkeypatch.setattr(config, "INTERVALO_HORAS", 0.33)
    monkeypatch.setattr(config, "TARIFA_KWH", 0.75)
    assert main.executar_pipeline() == 1
    assert not temp_db.exists()

    # 2. Tarifa negativa deve falhar antes de criar o banco
    monkeypatch.setattr(config, "INTERVALO_HORAS", 1.0)
    monkeypatch.setattr(config, "TARIFA_KWH", -1.0)
    assert main.executar_pipeline() == 1
    assert not temp_db.exists()


def test_suporte_intervalo_15_minutos_pipeline_completo(tmp_path):
    """Testa o suporte a dados em resolução de 15 minutos (0.25h):

    validação de grade (00, 15, 30, 45 min), rejeição de minutos fora de grade,
    detecção de lacunas de 15 min e execução ponta a ponta com cálculo dimensional exato.
    """
    import main
    from src.import_data import load_and_validate_csv, identificar_lacunas_temporais

    temp_csv = tmp_path / "medicoes_15min.csv"
    temp_db = tmp_path / "power_15min.db"
    temp_out = tmp_path / "relatorio_15min.csv"

    # 1. Validação de grade: 00, 15, 30, 45 são válidos; 08:07 viola a grade de 15 min
    csv_validacao = (
        "data_hora,potencia_kw\n"
        "2026-08-01 08:00,10.0\n"
        "2026-08-01 08:15,12.0\n"
        "2026-08-01 08:30,14.0\n"
        "2026-08-01 08:45,16.0\n"
        "2026-08-01 08:07,18.0\n"   # Fora da grade de 15 min
    )
    temp_csv_val = tmp_path / "teste_grade_15min.csv"
    temp_csv_val.write_text(csv_validacao, encoding="utf-8")

    df_valid, rel_val = load_and_validate_csv(temp_csv_val, intervalo_horas=0.25)
    assert rel_val["total_lidos"] == 5
    assert rel_val["registros_validos"] == 4
    assert rel_val["fora_contrato_horario"] == 1
    assert len(df_valid) == 4

    # 2. Detecção de lacunas em resolução de 15 minutos
    lacunas = identificar_lacunas_temporais(df_valid, intervalo_horas=0.25)
    assert len(lacunas) == 0  # 08:00 a 08:45 contíguo

    df_com_lacuna = pd.DataFrame({
        "data_hora": pd.to_datetime(["2026-08-01 08:00", "2026-08-01 08:30"]),  # 08:15 ausente
        "potencia_kw": [10.0, 12.0],
    })
    lacunas_15m = identificar_lacunas_temporais(df_com_lacuna, intervalo_horas=0.25)
    assert len(lacunas_15m) == 1
    assert lacunas_15m[0] == pd.Timestamp("2026-08-01 08:15:00")

    # 3. Execução ponta a ponta com 1 dia completo de 15 min (96 medições de 10 kW)
    # Energia esperada = 96 * (10.0 kW * 0.25h) = 240.0 kWh
    timestamps_1dia = pd.date_range("2026-08-01 00:00", "2026-08-01 23:45", freq="15min")
    assert len(timestamps_1dia) == 96

    linhas = ["data_hora,potencia_kw"] + [f"{ts.strftime('%Y-%m-%d %H:%M')},10.0" for ts in timestamps_1dia]
    temp_csv.write_text("\n".join(linhas), encoding="utf-8")

    status = main.executar_pipeline(
        csv_path=temp_csv,
        tarifa_kwh=1.0,
        database_path=temp_db,
        output_path=temp_out,
        intervalo_horas=0.25,
    )
    assert status == 0
    assert temp_db.exists()
    assert temp_out.exists()

    df_resultado = pd.read_csv(temp_out)
    assert len(df_resultado) == 1
    assert df_resultado["dia"].iloc[0] == "2026-08-01"
    assert df_resultado["total_medicoes"].iloc[0] == 96
    assert df_resultado["dia_completo"].iloc[0] == True
    assert df_resultado["consumo_kwh"].iloc[0] == 240.0
    assert df_resultado["potencia_media_kw"].iloc[0] == 10.0
    assert df_resultado["demanda_maxima_kw"].iloc[0] == 10.0



def test_pipeline_deteccao_lacunas_em_importacoes_distintas(tmp_path, monkeypatch, capsys):
    """Verifica que o pipeline acusa no relatório as lacunas geradas por

    lotes de dados cronologicamente separados importados sucessivamente no mesmo banco.
    """
    import main
    import config

    temp_db = tmp_path / "power_gaps.db"
    temp_out = tmp_path / "relatorio_gaps.csv"
    monkeypatch.setattr(config, "DATABASE_PATH", temp_db)
    monkeypatch.setattr(config, "OUTPUT_PATH", temp_out)
    monkeypatch.setattr(config, "INTERVALO_HORAS", 1.0)
    monkeypatch.setattr(config, "TARIFA_KWH", 0.75)

    # Lote 1: 01/08 (24 horas)
    csv_lote1 = tmp_path / "lote1.csv"
    linhas_lote1 = ["data_hora,potencia_kw"] + [f"2026-08-01 {h:02d}:00,10.0" for h in range(24)]
    csv_lote1.write_text("\n".join(linhas_lote1), encoding="utf-8")

    monkeypatch.setattr(config, "CSV_PATH", csv_lote1)
    assert main.executar_pipeline() == 0

    # Lote 2: 03/08 (24 horas) - O dia 02/08 está 100% ausente entre os lotes
    csv_lote2 = tmp_path / "lote2.csv"
    linhas_lote2 = ["data_hora,potencia_kw"] + [f"2026-08-03 {h:02d}:00,15.0" for h in range(24)]
    csv_lote2.write_text("\n".join(linhas_lote2), encoding="utf-8")

    monkeypatch.setattr(config, "CSV_PATH", csv_lote2)
    assert main.executar_pipeline() == 0

    saida = capsys.readouterr().out
    assert "AVISOS DO HISTÓRICO CONSOLIDADO" in saida
    assert "24 hora(s) ausente(s)" in saida
    assert "02/08/2026" in saida


def test_pipeline_e2e_com_banco_temporario_e_retorno_falhas(tmp_path, monkeypatch):
    """Testa a execução completa do pipeline com caminhos isolados e validação

    de retorno de código de erro quando há falhas críticas.
    """
    import main
    import config

    temp_csv = tmp_path / "medicoes.csv"
    temp_db = tmp_path / "power.db"
    temp_out = tmp_path / "relatorio.csv"

    csv_content = (
        "data_hora,potencia_kw\n"
        "2026-08-01 08:00,10.0\n"
        "2026-08-01 09:00,20.0\n"
    )
    temp_csv.write_text(csv_content, encoding="utf-8")

    monkeypatch.setattr(config, "CSV_PATH", temp_csv)
    monkeypatch.setattr(config, "DATABASE_PATH", temp_db)
    monkeypatch.setattr(config, "OUTPUT_PATH", temp_out)
    monkeypatch.setattr(config, "INTERVALO_HORAS", 1.0)
    monkeypatch.setattr(config, "TARIFA_KWH", 0.75)

    # 1. Execução com sucesso deve retornar 0
    status_sucesso = main.executar_pipeline()
    assert status_sucesso == 0
    assert temp_db.exists()
    assert temp_out.exists()

    # 2. Execução com CSV sem registros válidos deve retornar 1
    csv_invalido = tmp_path / "vazio.csv"
    csv_invalido.write_text("data_hora,potencia_kw\ninvalido,-50\n", encoding="utf-8")
    monkeypatch.setattr(config, "CSV_PATH", csv_invalido)
    assert main.executar_pipeline() == 1

    # 3. Execução com falha de exportação deve retornar 1
    monkeypatch.setattr(config, "CSV_PATH", temp_csv)
    diretorio_bloqueador = tmp_path / "bloqueado"
    diretorio_bloqueador.mkdir()
    monkeypatch.setattr(config, "OUTPUT_PATH", diretorio_bloqueador)
    assert main.executar_pipeline() == 1

    # 4. Execução com falha na criação do banco (arquivo bloqueando diretório) deve retornar 1
    arquivo_bloqueio = tmp_path / "arquivo_em_vez_de_pasta"
    arquivo_bloqueio.write_text("bloqueando pasta")
    db_impossivel = arquivo_bloqueio / "banco.db"
    monkeypatch.setattr(config, "DATABASE_PATH", db_impossivel)
    monkeypatch.setattr(config, "OUTPUT_PATH", temp_out)
    assert main.executar_pipeline() == 1


def test_cli_argumentos_e_execucao_customizada(tmp_path):
    """Testa o processamento de flags de linha de comando com argparse

    e a execução do pipeline com caminhos e parâmetros fornecidos via CLI.
    """
    import main
    import config
    from pathlib import Path

    # 1. Parsing com valores default
    args_default = main.parse_args([])
    assert args_default.csv_path == config.CSV_PATH
    assert args_default.tarifa_kwh == config.TARIFA_KWH
    assert args_default.database_path == config.DATABASE_PATH
    assert args_default.output_path == config.OUTPUT_PATH

    # 2. Parsing com argumentos explícitos
    custom_csv = tmp_path / "custom_medicoes.csv"
    custom_db = tmp_path / "custom.db"
    custom_out = tmp_path / "custom_relatorio.csv"

    argv = [
        "--csv", str(custom_csv),
        "--tarifa", "0.95",
        "--banco", str(custom_db),
        "--saida", str(custom_out),
    ]
    args_custom = main.parse_args(argv)
    assert args_custom.csv_path == custom_csv
    assert args_custom.tarifa_kwh == 0.95
    assert args_custom.database_path == custom_db
    assert args_custom.output_path == custom_out

    # 3. Execução direta passando parâmetros explicitamente
    custom_csv.write_text("data_hora,potencia_kw\n2026-08-01 08:00,12.0\n", encoding="utf-8")
    status = main.executar_pipeline(
        csv_path=args_custom.csv_path,
        tarifa_kwh=args_custom.tarifa_kwh,
        database_path=args_custom.database_path,
        output_path=args_custom.output_path,
    )
    assert status == 0
    assert custom_db.exists()
    assert custom_out.exists()


# ----------------------------------------------------------------------
# 6. Testes Diretos de Ingestão e Validação (import_data.py)
# ----------------------------------------------------------------------


def test_load_and_validate_csv_arquivo_inexistente_ou_vazio(tmp_path):
    """Verifica lançamento de FileNotFoundError para arquivo inexistente

    e ValueError para arquivo de tamanho zero.
    """
    # 1. Arquivo inexistente
    arquivo_inexistente = tmp_path / "nao_existe.csv"
    with pytest.raises(FileNotFoundError, match="Arquivo de medições não encontrado"):
        load_and_validate_csv(arquivo_inexistente)

    # 2. Arquivo vazio (0 bytes)
    arquivo_vazio = tmp_path / "vazio_zero_bytes.csv"
    arquivo_vazio.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="O arquivo CSV está vazio"):
        load_and_validate_csv(arquivo_vazio)


def test_load_and_validate_csv_estrutura_colunas_ausentes(tmp_path):
    """Verifica erro explicito quando colunas obrigatórias estão ausentes no CSV."""
    # Coluna potencia_kw ausente
    csv_sem_potencia = tmp_path / "sem_potencia.csv"
    csv_sem_potencia.write_text("data_hora,outra_coluna\n2026-08-01 08:00,10.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Colunas ausentes"):
        load_and_validate_csv(csv_sem_potencia)

    # Cabeçalho completamente errado
    csv_errado = tmp_path / "cabecalho_errado.csv"
    csv_errado.write_text("timestamp,valor\n2026-08-01 08:00,10.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Colunas esperadas"):
        load_and_validate_csv(csv_errado)


def test_load_and_validate_csv_apenas_cabecalho(tmp_path):
    """Verifica comportamento quando o CSV contém cabeçalhos válidos mas nenhuma linha de dados."""
    csv_so_cabecalho = tmp_path / "apenas_cabecalho.csv"
    csv_so_cabecalho.write_text("data_hora,potencia_kw\n", encoding="utf-8")

    df_valid, relatorio = load_and_validate_csv(csv_so_cabecalho)
    assert df_valid.empty
    assert list(df_valid.columns) == ["data_hora", "potencia_kw"]
    assert relatorio["total_lidos"] == 0
    assert relatorio["registros_validos"] == 0
    assert any("apenas cabeçalhos" in a for a in relatorio["avisos"])


def test_load_and_validate_csv_sem_linhas_validas(tmp_path):
    """Verifica que quando 100% das linhas lidas são inválidas, todas são contabilizadas

    como descartadas e um DataFrame vazio estruturado é retornado.
    """
    csv_todas_invalidas = tmp_path / "todas_invalidas.csv"
    conteudo = (
        "data_hora,potencia_kw\n"
        ",10.0\n"                     # data nula
        "2026-08-01 08:00,\n"         # potencia nula
        "2026-08-01 08:00,-15.0\n"    # potencia negativa
    )
    csv_todas_invalidas.write_text(conteudo, encoding="utf-8")

    df_valid, relatorio = load_and_validate_csv(csv_todas_invalidas)
    assert df_valid.empty
    assert relatorio["total_lidos"] == 3
    assert relatorio["registros_validos"] == 0
    assert relatorio["linhas_descartadas"] == 3
    assert relatorio["ausentes_descartados"] == 2
    assert relatorio["negativos_rejeitados"] == 1


def test_load_and_validate_csv_formato_iso_t_espacos_e_potencia_zero(tmp_path):
    """Verifica que formato ISO com 'T', espaços em branco extras em campos

    e potências exatamente zero (0.0 kW, instalação sem carga) são aceitos com sucesso.
    """
    csv_teste = tmp_path / "iso_espacos_zero.csv"
    conteudo = (
        "data_hora,potencia_kw\n"
        "2026-08-01T08:00,10.5\n"           # Formato ISO com 'T'
        "  2026-08-01 09:00  ,  15.0  \n"   # Espaços externos a serem limpos com strip
        "2026-08-01 10:00,0.0\n"            # Potência zero (válida fisicamente)
    )
    csv_teste.write_text(conteudo, encoding="utf-8")

    df_valid, relatorio = load_and_validate_csv(csv_teste)
    assert len(df_valid) == 3
    assert relatorio["total_lidos"] == 3
    assert relatorio["registros_validos"] == 3
    assert relatorio["linhas_descartadas"] == 0
    assert df_valid["potencia_kw"].iloc[2] == 0.0


def test_identificar_lacunas_e_resumo_casos_borda():
    """Testa casos de borda das funções de identificação e resumo de lacunas temporais."""
    # 1. Menos de 2 medições -> sem lacunas calculáveis
    assert identificar_lacunas_temporais(pd.DataFrame()) == []
    df_1linha = pd.DataFrame({"data_hora": [pd.Timestamp("2026-08-01 08:00")]})
    assert identificar_lacunas_temporais(df_1linha) == []

    # 2. Resumo de lacunas vazias
    assert formatar_resumo_lacunas([]) == []

    # 3. Resumo de lacunas com mais de 3 dias inteiramente ausentes (testa sufixo 'e mais X dia(s)')
    # Gera 4 dias inteiros (4 * 24 = 96 horas) ausentes
    lacunas_4dias = pd.date_range("2026-08-01 00:00", "2026-08-04 23:00", freq="1h")
    resumo_4dias = formatar_resumo_lacunas(list(lacunas_4dias), intervalo_horas=1.0)
    assert any("e mais 1 dia(s)" in msg for msg in resumo_4dias)


