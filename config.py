"""Configurações globais do projeto PowerMonitor."""

from pathlib import Path

# Diretório base do projeto
BASE_DIR = Path(__file__).resolve().parent

# Caminhos de arquivos e diretórios
DATA_DIR = BASE_DIR / "data"
DATABASE_DIR = BASE_DIR / "database"
OUTPUT_DIR = BASE_DIR / "output"
SQL_DIR = BASE_DIR / "sql"

CSV_PATH = DATA_DIR / "medicoes.csv"
DATABASE_PATH = DATABASE_DIR / "power_monitor.db"
OUTPUT_PATH = OUTPUT_DIR / "relatorio.csv"
SQL_QUERIES_PATH = SQL_DIR / "queries.sql"

# Parâmetros de Engenharia Elétrica e Tarifação
# Intervalo padrão entre medições (em horas)
INTERVALO_HORAS = 1.0

# Tarifa de energia elétrica configurável (R$/kWh)
# Observação: Valor de referência para simulação educacional, não representa tarifa regulada específica.
TARIFA_KWH = 0.75
