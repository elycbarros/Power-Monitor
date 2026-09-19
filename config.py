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

# Arquivos padrão de entrada, persistência, saída e consultas analíticas
CSV_PATH = DATA_DIR / "medicoes.csv"
DATABASE_PATH = DATABASE_DIR / "power_monitor.db"
OUTPUT_PATH = OUTPUT_DIR / "relatorio.csv"
SQL_QUERIES_PATH = SQL_DIR / "queries.sql"

# -----------------------------------------------------------------------------
# 2. Premissas de Engenharia Elétrica e Tarifação
# -----------------------------------------------------------------------------
# INTERVALO_HORAS: Intervalo de tempo regular (Δt) entre medições consecutivas, em horas.
# - Na integração numérica da energia (E = ∫ P dt ≈ Σ P_i * Δt), este fator converte
#   potência média (kW) em energia consumida (kWh).
# - O pipeline suporta: 1.0 (amostragem horária), 0.5 (30 min) e 0.25 (15 min, padrão
#   utilizado em medição para faturamento de consumidores do Grupo A pelas concessionárias).
INTERVALO_HORAS = 1.0

# TARIFA_KWH: Tarifa didática de energia elétrica em Reais por quilowatt-hora (R$/kWh).
# - Utilizada para simulação linear simples de custo financeiro: Custo = E * Tarifa.
# - Observação de Engenharia: Em tarifas reais (ex: Grupo A ou Tarifa Branca), a tarifação
#   é horossazonal (postos ponta e fora de ponta), com parcelas separadas para demanda
#   faturada (R$/kW) e consumo de energia (R$/kWh), além de bandeiras tarifárias e tributos.
TARIFA_KWH = 0.75

