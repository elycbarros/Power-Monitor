#!/usr/bin/env python3
"""PowerMonitor: Pipeline de Análise de Consumo e Demanda de Energia Elétrica.

Orquestra o fluxo de dados:
CSV → Validação → Pandas → SQLite → SQL → Indicadores → Relatório
"""

import sys
from pathlib import Path

# Adiciona o diretório raiz ao sys.path para permitir importações relativas/absolutas limpas
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from src.database import get_connection, create_tables, insert_medicoes, query_to_dataframe
from src.import_data import load_and_validate_csv
from src.analysis import gerar_indicadores_completos, calcular_consumo_diario
from src.report import exibir_relatorio_terminal, exportar_relatorio_csv


def executar_pipeline() -> int:
    """Executa todas as etapas do pipeline do PowerMonitor.

    Retorna 0 em caso de sucesso ou código diferente de zero em caso de erro.
    """
    print("\n[Iniciando PowerMonitor v1.0]")

    # 1. Carregar e Validar Dados do CSV
    print(f"-> Carregando arquivo de medições: {config.CSV_PATH.name}...")
    try:
        df_valid, relatorio_validacao = load_and_validate_csv(config.CSV_PATH)
    except FileNotFoundError as e:
        print(f"\n[ERRO] {e}")
        print("Certifique-se de que o arquivo 'data/medicoes.csv' exista antes de executar.")
        return 1
    except ValueError as e:
        print(f"\n[ERRO] Falha de validação no CSV: {e}")
        return 1

    total_lidos = relatorio_validacao["total_lidos"]
    validos = relatorio_validacao["registros_validos"]
    print(f"   Total de registros lidos: {total_lidos}")
    print(f"   Registros válidos: {validos}")

    # Exibir avisos de validação se houver
    if relatorio_validacao["avisos"]:
        print("   Alertas durante validação:")
        for aviso in relatorio_validacao["avisos"]:
            print(f"     * {aviso}")

    if df_valid.empty:
        print("\n[AVISO] Nenhum registro válido encontrado para processamento. Pipeline encerrado.")
        return 0

    # 2. Inicializar Banco de Dados SQLite
    print(f"-> Conectando ao banco de dados SQLite: {config.DATABASE_PATH.name}...")
    try:
        conn = get_connection(config.DATABASE_PATH)
        create_tables(conn)
    except RuntimeError as e:
        print(f"\n[ERRO] Falha ao configurar banco de dados: {e}")
        return 1

    # 3. Armazenar Medições no Banco
    print("-> Sincronizando medições válidas com o banco relacional...")
    try:
        novos_inseridos = insert_medicoes(conn, df_valid)
        print(f"   Novos registros inseridos: {novos_inseridos} (evitadas duplicações por data_hora).")
    except RuntimeError as e:
        print(f"\n[ERRO] Falha ao persistir dados: {e}")
        conn.close()
        return 1

    # 4. Executar Análises via SQL e Pandas
    print("-> Calculando indicadores de demanda, consumo e custos...")
    try:
        # Carregar dados persistidos para análise integrada
        query_total = "SELECT data_hora, potencia_kw FROM medicoes ORDER BY data_hora ASC;"
        df_db = query_to_dataframe(conn, query_total)

        # Geração dos indicadores técnicos de Engenharia Elétrica
        indicadores = gerar_indicadores_completos(
            df=df_db,
            tarifa_kwh=config.TARIFA_KWH,
            intervalo_horas=config.INTERVALO_HORAS,
        )

        # Análise diária consolidada
        df_diario = calcular_consumo_diario(
            df=df_db,
            intervalo_horas=config.INTERVALO_HORAS,
        )
    except Exception as e:
        print(f"\n[ERRO] Falha durante a análise de dados: {e}")
        conn.close()
        return 1
    finally:
        conn.close()

    # 5. Exibir Relatório no Terminal
    exibir_relatorio_terminal(indicadores, df_diario)

    # 6. Exportar Relatório para CSV
    try:
        exportar_relatorio_csv(indicadores, df_diario, config.OUTPUT_PATH)
        print(f"-> Relatório exportado com sucesso para: {config.OUTPUT_PATH}\n")
    except Exception as e:
        print(f"\n[AVISO] Não foi possível exportar o arquivo CSV: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(executar_pipeline())
