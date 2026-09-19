"""PowerMonitor: Pipeline de Análise de Consumo e Demanda de Energia Elétrica.

Responsabilidades deste módulo (Orquestrador da Aplicação):
- Ponto de entrada ("entry point") do sistema.
- Orquestra a transição de dados entre todas as camadas da aplicação:
  1. Ingestão e Saneamento: CSV bruto -> Validação de regras elétricas -> DataFrame limpo;
  2. Persistência Relacional: DataFrame -> Transação SQLite ACID -> Histórico persistente;
  3. Recuperação e Análise: Consulta SQL -> Séries temporais Pandas -> Indicadores de Engenharia;
  4. Apresentação: Indicadores -> Relatório formatado no Terminal e Exportação em CSV.

Conceitos de Programação e Engenharia de Software aplicados:
- 'Orquestração vs Implementação': O arquivo principal NÃO faz contas nem escreve SQL
  diretamente. Ele apenas delega para módulos especializados (`import_data`, `database`,
  `analysis`, `report`), atuando como um maestro de uma orquestra.
- 'Controle de Fluxo com Códigos de Saída (Exit Codes)':
  Retorna '0' quando a execução é bem-sucedida e '1' quando ocorrem erros de validação
  ou configuração. Isso permite integrar o script em rotinas agendadas (Cron, Airflow)
  ou pipelines de CI/CD (GitHub Actions) que monitoram o status do processo.
- 'Gerenciamento Defensivo de Recursos': Uso de blocos 'try...finally' para garantir
  o fechamento de conexões de banco de dados (`conn.close()`), mesmo diante de exceções.
- 'Interface de Linha de Comando (CLI) com argparse': Permite parametrização completa via flags
  sem editar o código-fonte, viabilizando testes automatizados e execuções paralelas seguras.
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
    """Configura e processa argumentos de linha de comando do PowerMonitor.

    Analogia & Utilidade:
        Assim como um relé de proteção ou medidor digital possui botões ou portas de
        comunicação para parametrização (ajuste de TC/TP, corrente nominal), um programa
        profissional recebe parâmetros pela linha de comando sem exigir alteração de código.

    Conceito de Programação:
        - Módulo 'argparse': Biblioteca padrão do Python para parsing robusto de flags CLI.
        - Valores padrão com 'config.py': Caso o usuário não especifique uma flag,
          o sistema assume as constantes centralizadas no arquivo de configuração.
        - Conversão automática de tipos ('type=Path', 'type=float'): Valida e converte
          os argumentos digitados como string para os tipos adequados antes da execução.
        - O parâmetro 'argv' opcional facilita testes unitários automatizados, permitindo
          passar listas simuladas (ex: `parse_args(["--tarifa", "0.85"])`) sem manipular `sys.argv`.

    Args:
        argv: Lista opcional de argumentos de linha de comando (default lê de sys.argv).

    Returns:
        argparse.Namespace com os argumentos parseados e validados.
    """
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
    """Executa sequencialmente todas as etapas do pipeline ETL e analítico do PowerMonitor.

    Analogia com Engenharia Elétrica:
        Representa a automação do fluxo completo de telemetria predial/industrial:
        1. Recepção dos dados de medição (leitura dos arquivos de registradores);
        2. Saneamento metrológico (descarte de ruídos, negativos, carimbos corrompidos);
        3. Armazenamento seguro em banco de dados histórico para auditoria legal;
        4. Diagnóstico de qualidade da série temporal (cobertura e lacunas por falta de energia);
        5. Consolidação de balanço de potência, energia acumulada, pico e fator de carga;
        6. Emissão do boletim diário de operação e planilha para faturamento.

    Conceito de Programação:
        - Pipeline ETL (Extract, Transform, Load) + Análise:
          Extract (CSV), Transform (limpeza e validação no Pandas), Load (SQLite transacional),
          Analytics (cálculos vetoriais e agrupamentos) e Presentation (CLI e CSV).
        - Princípio "Fail-Fast": Valida pré-condições (intervalo, tarifa, existência do arquivo)
          logo no início, abortando com mensagem explícita e código de erro antes de abrir o banco.
        - Gerenciamento de Conexão com 'try...finally': Garante que `conn.close()` seja executado
          mesmo se houver erro no meio do cálculo de indicadores, prevenindo travamentos ("locks")
          no arquivo SQLite.
        - Reutilização de Resultados: Aproveita o 'df_diario' retornado por 'gerar_indicadores_completos',
          evitando duplicar o processamento de agregação por dia.

    Args:
        csv_path: Caminho opcional do arquivo CSV (default: config.CSV_PATH).
        tarifa_kwh: Tarifa opcional em R$/kWh (default: config.TARIFA_KWH).
        database_path: Caminho opcional do banco SQLite (default: config.DATABASE_PATH).
        output_path: Caminho opcional para exportar o relatório CSV (default: config.OUTPUT_PATH).
        intervalo_horas: Passo temporal opcional em horas (default: config.INTERVALO_HORAS).

    Returns:
        0 se todo o pipeline concluiu com sucesso; 1 em caso de erro de configuração ou falha fatal.
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
