"""Módulo de persistência e gerenciamento do banco de dados SQLite."""

import sqlite3
from pathlib import Path
from typing import Optional, Union, Tuple, List, Any
import pandas as pd


def get_connection(db_path: Union[str, Path]) -> sqlite3.Connection:
    """Cria e retorna uma conexão com o banco de dados SQLite.

    Garante que o diretório pai exista antes de conectar, tratando erros de SO.
    """
    path = Path(db_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"Falha ao criar diretório do banco de dados em '{path.parent}': {e}") from e

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
    """Insere registros de medição no banco de dados com integridade transacional.

    Regras de Integridade:
    - Se uma medição já existe para o mesmo carimbo data/hora com exatamente a mesma potência,
      o registro é ignorado de forma idempotente.
    - Se uma medição já existe para o mesmo carimbo com valor numérico de potência diferente,
      dispara um ValueError explícito e REVERTE O LOTE INTEIRO via transação (ROLLBACK).
    - Novos registros são persistidos atomicamente.

    Retorna:
        int: Quantidade de novos registros efetivamente persistidos.
    """
    if df.empty:
        return 0

    # Normalizar registros para tuplas (dt_str, potencia_float)
    registros: List[Tuple[str, float]] = []
    for _, row in df.iterrows():
        dt_val = row["data_hora"]
        dt_str = dt_val.strftime("%Y-%m-%d %H:%M:%S") if hasattr(dt_val, "strftime") else str(dt_val)
        registros.append((dt_str, float(row["potencia_kw"])))

    # Execução transacional atômica
    cursor = conn.cursor()
    try:
        with conn:
            novos_para_inserir: List[Tuple[str, float]] = []
            for dt_str, pot_val in registros:
                cursor.execute("SELECT potencia_kw FROM medicoes WHERE data_hora = ?;", (dt_str,))
                row = cursor.fetchone()
                if row is not None:
                    pot_existente = float(row[0])
                    # Igualdade estrita: qualquer divergência numérica caracteriza conflito
                    if pot_existente != pot_val:
                        raise ValueError(
                            f"Conflito de integridade para o horário '{dt_str}': "
                            f"valor existente no banco ({pot_existente} kW) "
                            f"difere do novo valor ({pot_val} kW). "
                            f"Operação abortada e lote de importação revertido integralmente."
                        )
                    # Valor idêntico: manter idempotência
                    continue
                else:
                    novos_para_inserir.append((dt_str, pot_val))

            if novos_para_inserir:
                cursor.executemany(
                    "INSERT INTO medicoes (data_hora, potencia_kw) VALUES (?, ?);",
                    novos_para_inserir,
                )

        return len(novos_para_inserir)
    except ValueError:
        raise
    except sqlite3.Error as e:
        raise RuntimeError(f"Erro no banco de dados durante inserção de medições: {e}") from e


def query_to_dataframe(
    conn: sqlite3.Connection, query: str, params: Optional[Union[list, tuple, dict]] = None
) -> pd.DataFrame:
    """Executa uma consulta SQL e retorna o resultado como um DataFrame do Pandas.

    Garante que a coluna 'data_hora' seja convertida para datetime se presente.
    """
    try:
        df = pd.read_sql_query(query, conn, params=params)
        if "data_hora" in df.columns:
            df["data_hora"] = pd.to_datetime(df["data_hora"])
        return df
    except Exception as e:
        raise RuntimeError(f"Erro ao executar consulta SQL: {e}") from e
