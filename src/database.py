"""Módulo de persistência e gerenciamento do banco de dados SQLite."""

import sqlite3
from pathlib import Path
from typing import Optional, Union, Tuple, List, Any
import pandas as pd


def get_connection(db_path: Union[str, Path]) -> sqlite3.Connection:
    """Cria e retorna uma conexão com o banco de dados SQLite.

    Garante que o diretório pai exista antes de conectar.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
    except sqlite3.Error as e:
        raise RuntimeError(f"Erro ao conectar ao banco de dados em '{path}': {e}") from e


def create_tables(conn: sqlite3.Connection) -> None:
    """Cria as tabelas necessárias no banco de dados se não existirem."""
    ddl = """
    CREATE TABLE IF NOT EXISTS medicoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data_hora DATETIME NOT NULL UNIQUE,
        potencia_kw REAL NOT NULL
    );
    """
    try:
        with conn:
            conn.execute(ddl)
    except sqlite3.Error as e:
        raise RuntimeError(f"Erro ao criar tabelas no banco de dados: {e}") from e


def insert_medicoes(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Insere registros de medição no banco de dados.

    Utiliza 'INSERT OR IGNORE' para garantir idempotência caso o mesmo
    carimbo de data/hora já tenha sido registrado anteriormente.

    Retorna a quantidade de novos registros efetivamente inseridos.
    """
    if df.empty:
        return 0

    # Garantir formato de string ISO para persistência consistente no SQLite
    records: List[Tuple[str, float]] = []
    for _, row in df.iterrows():
        dt_val = row["data_hora"]
        dt_str = dt_val.strftime("%Y-%m-%d %H:%M:%S") if hasattr(dt_val, "strftime") else str(dt_val)
        records.append((dt_str, float(row["potencia_kw"])))

    sql = "INSERT OR IGNORE INTO medicoes (data_hora, potencia_kw) VALUES (?, ?);"

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM medicoes;")
        count_before = cursor.fetchone()[0]

        with conn:
            cursor.executemany(sql, records)

        cursor.execute("SELECT COUNT(*) FROM medicoes;")
        count_after = cursor.fetchone()[0]
        return count_after - count_before
    except sqlite3.Error as e:
        raise RuntimeError(f"Erro ao inserir medições no banco de dados: {e}") from e


def query_to_dataframe(
    conn: sqlite3.Connection, query: str, params: Optional[Union[list, tuple, dict]] = None
) -> pd.DataFrame:
    """Executa uma consulta SQL e retorna o resultado como um DataFrame do Pandas."""
    try:
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        raise RuntimeError(f"Erro ao executar consulta SQL: {e}") from e
