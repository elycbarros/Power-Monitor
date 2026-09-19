#!/usr/bin/env python3
"""PowerMonitor: Pipeline de Análise de Consumo e Demanda de Energia Elétrica.

Orquestra o fluxo de dados:
CSV → Validação → Pandas → SQLite → SQL → Indicadores → Relatório
"""

import argparse
import math
import sys
from pathlib import Path
from typing import Optional, Union, List

# Adiciona o diretório raiz ao sys.path para permitir importações relativas/absolutas limpas
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from src.database import get_connection, create_tables, insert_medicoes, query_to_dataframe
from src.import_data import load_and_validate_csv, identificar_lacunas_temporais, formatar_resumo_lacunas
from src.analysis import gerar_indicadores_completos
from src.report import exibir_relatorio_terminal, exportar_relatorio_csv


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Configura e processa argumentos de linha de comando do PowerMonitor."""
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="PowerMonitor: Pipeline de Análise de Consumo e Demanda de Energia Elétrica.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--csv",
        dest="csv_path",
        type=Path,
        default=config.CSV_PATH,
        help="Caminho do arquivo CSV de medições de entrada.",
    )
    parser.add_argument(
        "--tarifa",
        dest="tarifa_kwh",
        type=float,
        default=config.TARIFA_KWH,
        help="Tarifa didática de referência em R$/kWh.",
    )
    parser.add_argument(
        "--banco",
        dest="database_path",
        type=Path,
        default=config.DATABASE_PATH,
        help="Caminho do banco de dados SQLite persistente.",
    )
    parser.add_argument(
        "--saida",
        dest="output_path",
        type=Path,
        default=config.OUTPUT_PATH,
        help="Caminho para exportação do relatório consolidado em CSV.",
    )
    parser.add_argument(
        "--intervalo",
        dest="intervalo_horas",
        type=float,
        default=config.INTERVALO_HORAS,
        help="Intervalo regular entre medições em horas (0.25 para 15 min, 0.5 para 30 min, 1.0 para 1h).",
    )
    return parser.parse_args(argv)


def executar_pipeline(
    csv_path: Optional[Union[str, Path]] = None,
    tarifa_kwh: Optional[float] = None,
    database_path: Optional[Union[str, Path]] = None,
    output_path: Optional[Union[str, Path]] = None,
    intervalo_horas: Optional[float] = None,
) -> int:
    """Executa todas as etapas do pipeline do PowerMonitor.

    Permite sobrescrever caminhos e parâmetros globais definidos em config.py.
    Retorna 0 em caso de sucesso ou 1 em caso de erro/falha de integridade.
    """
    print("\n[Iniciando PowerMonitor v1.0]")

    csv_file = Path(csv_path) if csv_path is not None else config.CSV_PATH
    tarifa = tarifa_kwh if tarifa_kwh is not None else config.TARIFA_KWH
    db_file = Path(database_path) if database_path is not None else config.DATABASE_PATH
    out_file = Path(output_path) if output_path is not None else config.OUTPUT_PATH
    intervalo = intervalo_horas if intervalo_horas is not None else config.INTERVALO_HORAS

    # 1. Validação de Parâmetros de Configuração
    INTERVALOS_SUPORTADOS = (0.25, 0.5, 1.0)
    if intervalo not in INTERVALOS_SUPORTADOS:
        print(
            f"\n[ERRO DE CONFIGURAÇÃO] O PowerMonitor opera exclusivamente com intervalos "
            f"regulares de 15 minutos (0.25h), 30 minutos (0.5h) ou 1 hora (1.0h). "
            f"Valor configurado: {intervalo}."
        )
        return 1

    if not isinstance(tarifa, (int, float)) or not math.isfinite(tarifa) or tarifa < 0:
        print(
            f"\n[ERRO DE CONFIGURAÇÃO] Tarifa de energia inválida: {tarifa}. "
            f"Deve ser um número finito não negativo."
        )
        return 1

    # 2. Carregar e Validar Dados do CSV
    print(f"-> Carregando arquivo de medições: {csv_file.name} (intervalo: {intervalo}h)...")
    try:
        df_valid, relatorio_validacao = load_and_validate_csv(csv_file, intervalo_horas=intervalo)
    except FileNotFoundError as e:
        print(f"\n[ERRO] {e}")
        print("Certifique-se de que o arquivo CSV de entrada exista antes de executar.")
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
    print(f"-> Conectando ao banco de dados SQLite: {db_file.name}...")
    try:
        conn = get_connection(db_file)
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
            lacunas_historico = identificar_lacunas_temporais(df_db, intervalo_horas=intervalo)
            avisos_historico = []
            if lacunas_historico:
                resumo_hist = formatar_resumo_lacunas(lacunas_historico, intervalo_horas=intervalo)
                unidade_lac = "hora(s)" if intervalo == 1.0 else "medição(ões)"
                avisos_historico.append(
                    f"Detectada(s) {len(lacunas_historico)} {unidade_lac} ausente(s) no histórico acumulado entre "
                    f"{df_db['data_hora'].iloc[0].strftime('%d/%m/%Y %H:%M')} e "
                    f"{df_db['data_hora'].iloc[-1].strftime('%d/%m/%Y %H:%M')}. "
                    f"{' '.join(resumo_hist)}"
                )

            indicadores = gerar_indicadores_completos(
                df=df_db,
                tarifa_kwh=tarifa,
                intervalo_horas=intervalo,
            )

            # df_diario já calculado dentro de gerar_indicadores_completos
            df_diario = indicadores["df_diario"]
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
        exportar_relatorio_csv(indicadores, df_diario, out_file)
        print(f"-> Relatório exportado com sucesso para: {out_file}\n")
    except Exception as e:
        print(
            f"\n[ERRO] As medições foram persistidas no banco com sucesso, "
            f"mas a exportação do relatório CSV falhou: {e}"
        )
        return 1

    return 0


if __name__ == "__main__":
    cli_args = parse_args(sys.argv[1:])
    sys.exit(
        executar_pipeline(
            csv_path=cli_args.csv_path,
            tarifa_kwh=cli_args.tarifa_kwh,
            database_path=cli_args.database_path,
            output_path=cli_args.output_path,
            intervalo_horas=cli_args.intervalo_horas,
        )
    )
