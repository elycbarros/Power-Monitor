"""Módulo de persistência e gerenciamento do banco de dados SQLite.

Responsabilidades deste módulo:
- Estabelecer conexão com o banco SQLite local de forma segura.
- Criar o esquema relacional (tabela de medições) garantindo unicidade temporal.
- Persistir novos lotes com integridade transacional atômica (ACID), idempotência
  e detecção de conflitos de telemetria com reversão integral (ROLLBACK).
- Executar consultas SQL e converter resultados diretamente em DataFrames do Pandas.

Conceitos centrais de banco de dados aplicados aqui:
- SQL vs. Pandas: O banco relacional é a "fonte da verdade" persistente no disco;
  o Pandas é o motor analítico em memória RAM.
- Integridade referencial e unicidade: Restrição UNIQUE impede medições duplicadas.
- Transações com 'with conn': Garante que um lote seja gravado integralmente (COMMIT)
  ou cancelado por completo (ROLLBACK) se houver qualquer divergência de dados.
"""

import sqlite3
from pathlib import Path
from typing import Optional, Union, Tuple, List, Any
import pandas as pd


def get_connection(db_path: Union[str, Path]) -> sqlite3.Connection:
    """Cria e retorna uma conexão com o banco de dados SQLite.

    Premissas e Tratamento de Recursos:
    - Garante que a pasta pai exista antes da conexão (usando Path.mkdir).
    - Habilita verificação de chaves estrangeiras via 'PRAGMA foreign_keys = ON;'.
      (No SQLite, chaves estrangeiras vêm desabilitadas por padrão por compatibilidade legada).
    - Captura exceções do sistema operacional (OSError) e do banco (sqlite3.Error),
      re-lançando-as como RuntimeError com mensagens claras e contextualizadas.

    Args:
        db_path: Caminho no disco para o arquivo .db (ex: 'database/power_monitor.db').

    Returns:
        sqlite3.Connection: Objeto de conexão ativo com o SQLite.

    Exemplo:
        >>> conn = get_connection("database/teste.db")
        >>> type(conn)
        <class 'sqlite3.Connection'>
        >>> conn.close()
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
    """Cria a tabela de medições elétricas no SQLite caso ela ainda não exista.

    Estrutura da Tabela 'medicoes':
    - id: INTEGER PRIMARY KEY AUTOINCREMENT — Identificador numérico sequencial único.
    - data_hora: DATETIME NOT NULL UNIQUE — Carimbo cronológico do início do intervalo.
      A restrição UNIQUE é essencial: num circuito elétrico físico, não podem coexistir
      dois estados ou medições de potência distintos no exato mesmo carimbo de tempo.
    - potencia_kw: REAL NOT NULL — Potência ativa média demandada no intervalo (kW).

    Conceito de Programação: 'with conn' (Gerenciador de Contexto Transacional)
    - Em Python, o bloco 'with conn:' abre uma TRANSAÇÃO no banco.
    - Se o bloco terminar sem erros, o SQLite executa 'COMMIT' automaticamente.
    - Se ocorrer uma exceção dentro do bloco, o SQLite executa 'ROLLBACK' automaticamente.
    - IMPORTANTE: 'with conn' NÃO fecha a conexão; apenas confirma ou cancela a transação.
      O fechamento do arquivo do banco é de responsabilidade de 'conn.close()'.
    """
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
    """Insere registros de medição no banco de dados com garantia de integridade transacional.

    Regras de Negócio e de Engenharia Elétrica:
    1. Idempotência:
       Se uma medição já existe no banco com exatamente o mesmo timestamp e a mesma potência,
       o registro é ignorado silenciosamente. Reexecutar o pipeline sobre os mesmos dados não
       gera erro nem duplica valores.
    2. Detecção de Conflito de Telemetria:
       Se o carimbo já existe no banco mas com potência diferente (ex: 10 kW no banco vs. 20 kW
       no novo lote), isto indica corrupção de dados ou divergência de sensores. O sistema
       dispara um ValueError imediato e o bloco 'with conn' executa ROLLBACK total, garantindo
       que nenhuma linha do lote conflitante seja persistida (propriedade de Atomicidade do ACID).
    3. Inserção em Lote (Batch):
       Novos registros válidos são acumulados e gravados de uma só vez com 'cursor.executemany',
       que é ordens de grandeza mais eficiente do que inserções individuais linha a linha.

    Conceito de Programação: Consultas Parametrizadas com '?'
    - A consulta 'SELECT potencia_kw FROM medicoes WHERE data_hora = ?;' utiliza o caractere '?'
      como marcador de posição (placeholder).
    - O valor real é passado na tupla separada '(dt_str,)'.
    - Por que fazer assim?
      1. Segurança: Previne ataques de injeção de SQL (SQL Injection).
      2. Performance: Permite ao SQLite compilar o plano de execução da consulta uma única vez
         e reutilizá-lo para milhares de registros.

    Args:
        conn: Conexão ativa com o banco SQLite.
        df: DataFrame contendo as colunas 'data_hora' e 'potencia_kw'.

    Returns:
        int: Quantidade de registros novos efetivamente inseridos no banco.

    Exemplo:
        >>> # df com 2 linhas inéditas:
        >>> # insert_medicoes(conn, df) -> 2
        >>> # reexecutar com o mesmo df (idempotência):
        >>> # insert_medicoes(conn, df) -> 0
    """
    if df.empty:
        return 0

    # Normalizar registros em memória para tuplas puras de Python: (str_timestamp, float_potencia)
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
                # Consulta parametrizada com placeholder '?'
                cursor.execute("SELECT potencia_kw FROM medicoes WHERE data_hora = ?;", (dt_str,))
                row = cursor.fetchone()
                if row is not None:
                    pot_existente = float(row[0])
                    # Igualdade estrita: qualquer divergência numérica caracteriza conflito de medição
                    if pot_existente != pot_val:
                        raise ValueError(
                            f"Conflito de integridade para o horário '{dt_str}': "
                            f"valor existente no banco ({pot_existente} kW) "
                            f"difere do novo valor ({pot_val} kW). "
                            f"Operação abortada e lote de importação revertido integralmente."
                        )
                    # Valor idêntico: manter idempotência (ignorar sem duplicar)
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
        # Re-lança o erro de integridade de dados para ser tratado pela camada superior (main.py)
        raise
    except sqlite3.Error as e:
        raise RuntimeError(f"Erro no banco de dados durante inserção de medições: {e}") from e


def query_to_dataframe(
    conn: sqlite3.Connection, query: str, params: Optional[Union[list, tuple, dict]] = None
) -> pd.DataFrame:
    """Executa uma consulta SQL analítica e converte o resultado diretamente em DataFrame Pandas.

    Por que usar pd.read_sql_query?
    - Esta função do Pandas faz a ponte entre o paradigma relacional (tabelas em disco)
      e o paradigma tabular/vetorizado (DataFrames em memória).
    - No SQLite, colunas de data/hora são armazenadas como texto formatado (ISO-8601).
      Portanto, convertemos explicitamente 'data_hora' com pd.to_datetime para restabelecer
      as capacidades de indexação e cálculo de séries temporais do Pandas.

    Args:
        conn: Conexão ativa com o SQLite.
        query: Consulta SQL completa (string).
        params: Parâmetros opcionais para preencher placeholders '?' na query.

    Returns:
        pd.DataFrame: Dados resultantes da consulta com tipos ajustados.
    """
    try:
        df = pd.read_sql_query(query, conn, params=params)
        if "data_hora" in df.columns:
            df["data_hora"] = pd.to_datetime(df["data_hora"])
        return df
    except Exception as e:
        raise RuntimeError(f"Erro ao executar consulta SQL: {e}") from e

