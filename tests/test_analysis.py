"""Testes unitários para o módulo de análise e validação do PowerMonitor."""

import pytest
import pandas as pd
import tempfile
from pathlib import Path

from src.analysis import (
    calcular_potencia_media,
    calcular_demanda_maxima,
    calcular_consumo_total,
    calcular_consumo_diario,
    calcular_custo_estimado,
    gerar_indicadores_completos,
)
from src.import_data import load_and_validate_csv
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


def test_calculo_potencia_media(dados_exemplo):
    """Verifica se a média de potência (kW) é calculada corretamente."""
    # Média: (10 + 20 + 30 + 20) / 4 = 20.0 kW
    media = calcular_potencia_media(dados_exemplo)
    assert media == 20.0


def test_calculo_demanda_maxima(dados_exemplo):
    """Verifica identificação da maior demanda e do horário correspondente."""
    demanda_max, horario = calcular_demanda_maxima(dados_exemplo)
    assert demanda_max == 30.0
    assert "01/08/2026 10:00" in horario


def test_calculo_consumo_total(dados_exemplo):
    """Verifica se a energia em kWh considera o intervalo regular em horas.

    Para intervalo_horas = 1.0 h:
    Energia = (10*1) + (20*1) + (30*1) + (20*1) = 80.0 kWh
    """
    consumo = calcular_consumo_total(dados_exemplo, intervalo_horas=1.0)
    assert consumo == 80.0

    # Testando com intervalo de 30 minutos (0.5 h)
    consumo_meia_hora = calcular_consumo_total(dados_exemplo, intervalo_horas=0.5)
    assert consumo_meia_hora == 40.0


def test_calculo_custo_estimado():
    """Verifica se o custo financeiro é proporcional ao consumo e à tarifa."""
    # 100 kWh * R$ 0.75/kWh = R$ 75.00
    custo = calcular_custo_estimado(consumo_kwh=100.0, tarifa_kwh=0.75)
    assert custo == 75.0


def test_calculo_custo_estimado_valores_invalidos():
    """Garante que tarifas ou consumos negativos levantam exceção."""
    with pytest.raises(ValueError):
        calcular_custo_estimado(consumo_kwh=-10.0, tarifa_kwh=0.75)

    with pytest.raises(ValueError):
        calcular_custo_estimado(consumo_kwh=50.0, tarifa_kwh=-0.50)


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


def test_validacao_valores_ausentes_e_invalidos(tmp_path):
    """Garante que registros com datas inválidas ou campos ausentes são tratados."""
    csv_content = (
        "data_hora,potencia_kw\n"
        "2026-08-01 08:00,10.0\n"
        "data_invalida,12.0\n"
        "2026-08-01 10:00,abc\n"
        "2026-08-01 11:00,\n"
        "2026-08-01 12:00,15.0\n"
    )
    temp_csv = tmp_path / "teste_invalidos.csv"
    temp_csv.write_text(csv_content, encoding="utf-8")

    df_valid, relatorio = load_and_validate_csv(temp_csv)

    assert len(df_valid) == 2
    assert relatorio["invalidos_conversao"] == 3


def test_calculo_consumo_diario():
    """Testa o agrupamento diário com múltiplos dias."""
    df = pd.DataFrame(
        {
            "data_hora": pd.to_datetime(
                [
                    "2026-08-01 10:00",
                    "2026-08-01 11:00",
                    "2026-08-02 10:00",
                    "2026-08-02 11:00",
                ]
            ),
            "potencia_kw": [10.0, 20.0, 15.0, 25.0],
        }
    )

    diario = calcular_consumo_diario(df, intervalo_horas=1.0)
    assert len(diario) == 2
    assert diario.loc[diario["dia"] == "2026-08-01", "consumo_kwh"].iloc[0] == 30.0
    assert diario.loc[diario["dia"] == "2026-08-02", "consumo_kwh"].iloc[0] == 40.0
    assert diario.loc[diario["dia"] == "2026-08-02", "demanda_maxima_kw"].iloc[0] == 25.0


def test_database_e_persistencia(tmp_path):
    """Testa criação de banco em memória temporária e inserção idempotente."""
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    create_tables(conn)

    df = pd.DataFrame(
        {
            "data_hora": pd.to_datetime(["2026-08-01 08:00:00", "2026-08-01 09:00:00"]),
            "potencia_kw": [12.5, 18.0],
        }
    )

    # Primeira inserção: 2 registros inseridos
    inseridos_1 = insert_medicoes(conn, df)
    assert inseridos_1 == 2

    # Segunda inserção dos mesmos dados: 0 inseridos devido ao UNIQUE
    inseridos_2 = insert_medicoes(conn, df)
    assert inseridos_2 == 0

    df_res = query_to_dataframe(conn, "SELECT * FROM medicoes")
    assert len(df_res) == 2

    conn.close()
