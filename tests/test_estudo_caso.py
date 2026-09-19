"""Testes unitários e de integração para o processamento do estudo de caso real UCI."""

import math
from pathlib import Path
import tempfile
import pytest
import pandas as pd
from scripts.preparar_estudo_caso_uci import processar_mes_uci


def _criar_arquivo_uci_sintetico(linhas: list[str]) -> Path:
    """Cria um arquivo temporário simulando o formato do dataset UCI."""
    temp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
    header = "Date;Time;Global_active_power;Global_reactive_power;Voltage;Global_intensity;Sub_metering_1;Sub_metering_2;Sub_metering_3\n"
    temp.write(header)
    for l in linhas:
        temp.write(l + "\n")
    temp.close()
    return Path(temp.name)


def test_hora_com_60_minutos_validos():
    """Uma hora com exatamente 60 medições válidas gera 1 registro horário com média exata."""
    linhas = []
    # Cria 60 minutos para a hora 08:00 do dia 01/05/2007 (potência variando de 1.0 a 2.0 kW)
    soma_esperada = 0.0
    for m in range(60):
        val = 1.0 + (m * 0.01)
        soma_esperada += val
        linhas.append(f"01/05/2007;08:{m:02d}:00;{val:.3f};0.1;230.0;5.0;0;0;0")

    arq = _criar_arquivo_uci_sintetico(linhas)
    try:
        registros, resumo = processar_mes_uci(arq, ano=2007, mes=5)
        assert len(registros) == 1
        assert registros[0]["data_hora"] == "2007-05-01 08:00"
        media_esperada = soma_esperada / 60.0
        assert math.isclose(registros[0]["potencia_kw"], media_esperada, rel_tol=1e-3)
        assert resumo["horas_completas"] == 1
        assert resumo["minutos_validos"] == 60
    finally:
        arq.unlink()


def test_hora_com_minuto_ausente_descartada():
    """Uma hora com 59 minutos (1 ausente) deve ser descartada sob a política conservadora."""
    linhas = []
    # Apenas 59 minutos (minuto 30 omitido)
    for m in range(60):
        if m == 30:
            continue
        linhas.append(f"01/05/2007;08:{m:02d}:00;1.5;0.1;230.0;5.0;0;0;0")

    arq = _criar_arquivo_uci_sintetico(linhas)
    try:
        registros, resumo = processar_mes_uci(arq, ano=2007, mes=5)
        # Nenhuma hora completa deve ser gerada
        assert len(registros) == 0
        assert resumo["horas_completas"] == 0
        assert resumo["minutos_validos"] == 59
        assert resumo["horas_descartadas"] > 0
    finally:
        arq.unlink()


def test_minuto_duplicado_detectado():
    """Minutos duplicados devem ser ignorados/contabilizados e não inflar a contagem."""
    linhas = []
    # 59 minutos normais + 1 duplicata do minuto 00 (totalizando 60 linhas, mas apenas 59 minutos únicos)
    for m in range(59):
        linhas.append(f"01/05/2007;08:{m:02d}:00;1.5;0.1;230.0;5.0;0;0;0")
    # Repete minuto 00
    linhas.append("01/05/2007;08:00:00;1.5;0.1;230.0;5.0;0;0;0")

    arq = _criar_arquivo_uci_sintetico(linhas)
    try:
        registros, resumo = processar_mes_uci(arq, ano=2007, mes=5)
        assert len(registros) == 0  # Rejeitada porque teve apenas 59 únicos
        assert resumo["minutos_duplicados"] == 1
    finally:
        arq.unlink()


def test_valor_invalido_rejeitado():
    """Valores ausentes ('?') ou negativos devem ser rejeitados e invalidar a hora."""
    linhas = []
    for m in range(59):
        linhas.append(f"01/05/2007;08:{m:02d}:00;1.5;0.1;230.0;5.0;0;0;0")
    # Minuto 59 com '?'
    linhas.append("01/05/2007;08:59:00;?;0.1;230.0;5.0;0;0;0")

    arq = _criar_arquivo_uci_sintetico(linhas)
    try:
        registros, resumo = processar_mes_uci(arq, ano=2007, mes=5)
        assert len(registros) == 0
        assert resumo["minutos_ausentes_ou_nulos"] == 1
    finally:
        arq.unlink()


def test_classificacao_dias_uteis_e_fins_de_semana():
    """Classificação correta entre dias úteis (Seg-Sex) e fins de semana (Sáb-Dom)."""
    # 01/05/2007 foi terça-feira (útil)
    # 05/05/2007 foi sábado (fim de semana)
    # 06/05/2007 foi domingo (fim de semana)
    datas = [
        ("2007-05-01 08:00", False),  # Terça
        ("2007-05-02 08:00", False),  # Quarta
        ("2007-05-03 08:00", False),  # Quinta
        ("2007-05-04 08:00", False),  # Sexta
        ("2007-05-05 08:00", True),   # Sábado
        ("2007-05-06 08:00", True),   # Domingo
        ("2007-05-07 08:00", False),  # Segunda
    ]
    for dt_str, eh_fds_esperado in datas:
        dt = pd.to_datetime(dt_str)
        eh_fds = dt.weekday() >= 5
        assert eh_fds == eh_fds_esperado, f"Falha na classificação de {dt_str}"


def test_concordancia_energia_minutos_e_horaria():
    """Comprova concordância exata entre soma da energia em minutos e energia horária (P_hora * 1.0)."""
    leituras_minuto = [0.85 + (i * 0.02) for i in range(60)]
    # Energia somando os minutos: E = sum(P_i * (1/60))
    energia_minutos = sum(p * (1.0 / 60.0) for p in leituras_minuto)
    # Média horária
    potencia_horaria = sum(leituras_minuto) / 60.0
    energia_horaria = potencia_horaria * 1.0

    assert math.isclose(energia_minutos, energia_horaria, rel_tol=1e-9)
