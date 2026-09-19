#!/usr/bin/env python3
"""PowerMonitor: Pipeline de Análise de Consumo e Demanda de Energia Elétrica.

Orquestra o fluxo de dados:
CSV → Validação → Pandas → SQLite → SQL → Indicadores → Relatório
"""

import math
import sys
from pathlib import Path

# Adiciona o diretório raiz ao sys.path para permitir importações relativas/absolutas limpas
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from src.database import get_connection, create_tables, insert_medicoes, query_to_dataframe
from src.import_data import load_and_validate_csv, identificar_lacunas_temporais, formatar_resumo_lacunas
from src.analysis import gerar_indicadores_completos, calcular_consumo_diario
from src.report import exibir_relatorio_terminal, exportar_relatorio_csv


def executar_pipeline() -> int:
    """Executa todas as etapas do pipeline do PowerMonitor.

    Retorna 0 em caso de sucesso ou 1 em caso de erro/falha de integridade.
    """
    print("\n[Iniciando PowerMonitor v1.0]")

    # 1. Validação de Parâmetros Globais de Configuração
    if config.INTERVALO_HORAS != 1.0:
        print(
            f"\n[ERRO DE CONFIGURAÇÃO] O PowerMonitor v1.0 opera exclusivamente com medições "
            f"em intervalos de uma hora (INTERVALO_HORAS = 1.0). Valor configurado: {config.INTERVALO_HORAS}."
        )
        return 1

    if not isinstance(config.TARIFA_KWH, (int, float)) or not math.isfinite(config.TARIFA_KWH) or config.TARIFA_KWH < 0:
        print(
            f"\n[ERRO DE CONFIGURAÇÃO] Tarifa de energia inválida: {config.TARIFA_KWH}. "
            f"Deve ser um número finito não negativo."
        )
        return 1

    # 2. Carregar e Validar Dados do CSV
    print(f"-> Carregando arquivo de medições: {config.CSV_PATH.name}...")
    try:
        df_valid, relatorio_validacao = load_and_validate_csv(config.CSV_PATH)
    except FileNotFoundError as e:
        print(f"\n[ERRO] {e}")
        print("Certifique-se de que o arquivo 'data/medicoes.csv' exista antes de executar.")
        return 1
    except ValueError as e:
        print(f"\n[ERRO DE VALIDAÇÃO] Falha ao processar CSV: {e}")
        return 1

    total_lidos = relatorio_validacao["total_lidos"]
    validos = relatorio_validacao["registros_validos"]
    descartados = relatorio_validacao["linhas_descartadas"]

    print(f"   Linhas totais lidas: {total_lidos}")
    print(f"   Medições válidas no lote: {validos}")
    if descartados > 0:
        print(f"   Linhas descartadas na validação: {descartados}")

    if relatorio_validacao["avisos"]:
        print("   Observações da validação do lote:")
        for aviso in relatorio_validacao["avisos"]:
            print(f"     * {aviso}")

    if df_valid.empty:
        print("\n[ERRO] Nenhum registro válido encontrado no arquivo para processamento. Pipeline abortado.")
        return 1

    # 3. Conectar ao Banco de Dados SQLite e Garantir Fechamento
    print(f"-> Conectando ao banco de dados SQLite: {config.DATABASE_PATH.name}...")
    try:
        conn = get_connection(config.DATABASE_PATH)
    except RuntimeError as e:
        print(f"\n[ERRO] Falha ao conectar ao banco de dados: {e}")
        return 1

    novos_inseridos = 0
    try:
        try:
            create_tables(conn)
        except RuntimeError as e:
            print(f"\n[ERRO] Falha ao inicializar tabelas do banco de dados: {e}")
            return 1

        # 4. Armazenar Medições no Banco com Integridade Transacional
        print("-> Sincronizando medições válidas com o banco relacional...")
        try:
            novos_inseridos = insert_medicoes(conn, df_valid)
            print(f"   Novas medições persistidas: {novos_inseridos} (reimportações idênticas mantidas idempotentes).")
        except ValueError as e:
            print(f"\n[ERRO DE INTEGRIDADE] Transação abortada com rollback: {e}")
            return 1
        except RuntimeError as e:
            print(f"\n[ERRO] Falha na persistência de dados: {e}")
            return 1

        # 5. Executar Análises sobre o Histórico Consolidado no Banco
        print("-> Calculando indicadores técnicos sobre o histórico acumulado...")
        try:
            query_total = "SELECT data_hora, potencia_kw FROM medicoes ORDER BY data_hora ASC;"
            df_db = query_to_dataframe(conn, query_total)

            # Verificar lacunas temporais no histórico acumulado
            lacunas_historico = identificar_lacunas_temporais(df_db)
            avisos_historico = []
            if lacunas_historico:
                resumo_hist = formatar_resumo_lacunas(lacunas_historico)
                avisos_historico.append(
                    f"Detectada(s) {len(lacunas_historico)} hora(s) ausente(s) no histórico acumulado entre "
                    f"{df_db['data_hora'].iloc[0].strftime('%d/%m/%Y %H:%M')} e "
                    f"{df_db['data_hora'].iloc[-1].strftime('%d/%m/%Y %H:%M')}. "
                    f"{' '.join(resumo_hist)}"
                )

            indicadores = gerar_indicadores_completos(
                df=df_db,
                tarifa_kwh=config.TARIFA_KWH,
                intervalo_horas=config.INTERVALO_HORAS,
            )

            df_diario = calcular_consumo_diario(
                df=df_db,
                intervalo_horas=config.INTERVALO_HORAS,
            )
        except Exception as e:
            print(f"\n[ERRO] Falha durante o cálculo de indicadores: {e}")
            return 1

    finally:
        conn.close()

    # 6. Exibir Relatório no Terminal
    estatisticas_lote = {
        "total_lidos": total_lidos,
        "registros_validos": validos,
        "linhas_descartadas": descartados,
        "novos_inseridos": novos_inseridos,
    }

    exibir_relatorio_terminal(
        indicadores=indicadores,
        df_diario=df_diario,
        estatisticas_lote=estatisticas_lote,
        avisos_lote=relatorio_validacao["avisos"],
        avisos_historico=avisos_historico,
    )

    # 7. Exportar Relatório para CSV
    try:
        exportar_relatorio_csv(indicadores, df_diario, config.OUTPUT_PATH)
        print(f"-> Relatório exportado com sucesso para: {config.OUTPUT_PATH}\n")
    except Exception as e:
        print(
            f"\n[ERRO] As medições foram persistidas no banco com sucesso, "
            f"mas a exportação do relatório CSV falhou: {e}"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(executar_pipeline())
