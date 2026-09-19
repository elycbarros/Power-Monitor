"""Configurações globais do projeto PowerMonitor.

Este módulo centraliza os caminhos do sistema de arquivos e as premissas
técnicas e tarifárias de Engenharia Elétrica adotadas pelo pipeline.

Por que centralizar configurações em um arquivo dedicado?
- Em engenharia de software, evitar "números mágicos" espalhados pelo código
  facilita a manutenção e parametrização.
- Por convenção do Python (PEP 8), constantes globais são escritas em MAIÚSCULAS.
"""

from pathlib import Path

# -----------------------------------------------------------------------------
# 1. Estrutura de Diretórios e Arquivos
# -----------------------------------------------------------------------------
# BASE_DIR localiza dinamicamente a pasta raiz do projeto a partir deste arquivo,
# garantindo que caminhos relativos funcionem independentemente de onde o script é chamado.
BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
DATABASE_DIR = BASE_DIR / "database"
OUTPUT_DIR = BASE_DIR / "output"
SQL_DIR = BASE_DIR / "sql"

# Arquivos padrão de entrada, persistência, saídas (CSV e HTML) e consultas analíticas
CSV_PATH = DATA_DIR / "medicoes.csv"
DATABASE_PATH = DATABASE_DIR / "power_monitor.db"
OUTPUT_PATH = OUTPUT_DIR / "relatorio.csv"
HTML_OUTPUT_PATH = OUTPUT_DIR / "relatorio.html"
SQL_QUERIES_PATH = SQL_DIR / "queries.sql"

# -----------------------------------------------------------------------------
# 2. Premissas de Engenharia Elétrica e Tarifação
# -----------------------------------------------------------------------------
# INTERVALO_HORAS: Intervalo de tempo regular (Δt) entre medições consecutivas, em horas.
# - Na integração da energia ativa (E = P_média * Δt), este fator converte
#   potência média (kW) em energia consumida (kWh). Essa é uma relação física de conversão.
# - O pipeline suporta intervalos de: 1.0 (1h), 0.5 (30 min) e 0.25 (15 min).
#   A resolução de 15 minutos é uma capacidade técnica de amostragem temporal dos dados
#   e não torna o PowerMonitor um sistema de apuração de faturamento regulatório.
INTERVALO_HORAS = 1.0

# TARIFA_KWH: Tarifa didática de referência em Reais por quilowatt-hora (R$/kWh).
# - Utilizada para simulação simplificada de custo: Custo = E * Tarifa.
# - Trata-se de uma hipótese de cálculo configurável; não representa fatura de energia
#   nem valor devido à distribuidora.
# - Distinção regulatória (REN ANEEL nº 1.000/2021):
#   * No Grupo A (Art. 294), há cobrança de demanda de potência (em R$/kW) e de consumo
#     de energia ativa (em R$/kWh), diferenciada por postos horários (ponta e fora de ponta).
#   * Na Modalidade Horária Branca do Grupo B (Art. 212), há apenas diferenciação da tarifa
#     de consumo de energia ativa (em R$/kWh) entre postos ponta, intermediário e fora de ponta,
#     sem cobrança de demanda em R$/kW.
#   * O PowerMonitor não calcula faturamento regulado, custo de disponibilidade, ultrapassagem,
#     bandeiras tarifárias ou tributos (ICMS/PIS/COFINS).
TARIFA_KWH = 0.75

