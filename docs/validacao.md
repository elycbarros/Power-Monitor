# Validação e Reprodutibilidade de Resultados

Este documento descreve como reproduzir os resultados do **PowerMonitor (v1.0)**, detalha a suíte de testes automatizados e apresenta a análise crítica de cobertura.

---

## 1. Como Reproduzir os Resultados

### 1.1 Execução Padrão

A partir do diretório raiz do projeto:

```bash
# 1. Ativar o ambiente virtual com as dependências instaladas
source .venv/bin/activate  # ou .venv\Scripts\activate no Windows

# 2. Executar o pipeline principal
python main.py
```

O pipeline lerá `data/medicoes.csv`, atualizará `database/power_monitor.db`, exibirá o relatório no terminal e gravará o arquivo local `output/relatorio.csv`.

### 1.2 Execução Isolada (Ambiente Temporário)

Para reproduzir os resultados sem modificar o banco `database/power_monitor.db` nem sobrescrever `output/relatorio.csv`:

```python
import tempfile
from pathlib import Path
import config, main

with tempfile.TemporaryDirectory() as tmpdir:
    tpath = Path(tmpdir)
    config.DATABASE_PATH = tpath / "temp_power.db"
    config.OUTPUT_PATH = tpath / "temp_relatorio.csv"
    
    codigo_saida = main.executar_pipeline()
    assert codigo_saida == 0, f"Falha na execução do pipeline (código {codigo_saida})"
    print("\n[Verificação Concluída]: Pipeline validado com sucesso em ambiente isolado.")
```

---

## 2. Mapa dos Testes Automatizados (`tests/test_analysis.py`)

A suíte conta com **28 testes automatizados** cobrindo unidades de cálculo elétrico, integridade de ingestão, persistência relacional, concordância com consultas SQL e execução ponta a ponta:

| # | Teste | Camada | Invariante / Comportamento Verificado |
|---|---|---|---|
| 1 | `test_calculo_potencia_media` | [`src/analysis.py`](../src/analysis.py) | Média aritmética correta para medições em kW. |
| 2 | `test_calculo_demanda_maxima` | [`src/analysis.py`](../src/analysis.py) | Identificação do valor de pico e respectivo timestamp formatado. |
| 3 | `test_calculo_demanda_maxima_desempate_deterministico` | [`src/analysis.py`](../src/analysis.py) | Desempate determinístico selecionando a primeira ocorrência em caso de empates. |
| 4 | `test_calculo_consumo_total` | [`src/analysis.py`](../src/analysis.py) | Cálculo da integral de energia $\sum (P \times \Delta t)$ para $\Delta t = 1{,}0\text{ h}$ e $\Delta t = 0{,}5\text{ h}$. |
| 5 | `test_calculo_custo_estimado` | [`src/analysis.py`](../src/analysis.py) | Proporcionalidade linear direta entre energia e tarifa em R$. |
| 6 | `test_validacao_intervalo_horas` | [`src/analysis.py`](../src/analysis.py) | Rejeição de $\Delta t \le 0$, `inf` ou `nan` com `ValueError`. |
| 7 | `test_validacao_custo_estimado_valores_invalidos` | [`src/analysis.py`](../src/analysis.py) | Rejeição de consumo ou tarifa negativos, `nan` ou `inf`. |
| 8 | `test_calculo_consumo_diario` | [`src/analysis.py`](../src/analysis.py) | Agrupamento diário e exigência de medições proporcionais a $\Delta t$ para classificar `dia_completo`. |
| 9 | `test_fator_carga_cenarios` | [`src/analysis.py`](../src/analysis.py) | Cálculo para carga constante ($FC = 1{,}0$), variável ($0 < FC < 1$) e potência zero ($FC = \text{None}$, sem divisão por zero). |
| 10 | `test_cobertura_medicoes_cenarios` | [`src/analysis.py`](../src/analysis.py) | Cálculo de horas esperadas, medidas e ausentes para série completa, lacunas, medição única e bordas parciais. |
| 11 | `test_participacao_diaria_e_energia_zero` | [`src/analysis.py`](../src/analysis.py) | Proporção diária em % frente ao total e tratamento seguro quando energia total for nula ($E_{\text{tot}} = 0$). |
| 12 | `test_desempate_dia_maior_consumo` | [`src/analysis.py`](../src/analysis.py) | Desempate determinístico selecionando a data mais antiga em caso de mesmo consumo diário. |
| 13 | `test_sintese_executiva_dados_incompletos` | [`src/analysis.py`](../src/analysis.py) | Geração de síntese interpretativa coerente com lacunas e dias parciais, sem inferir desperdício sem medições adicionais. |
| 14 | `test_rejeicao_potencia_negativa` | [`src/import_data.py`](../src/import_data.py) | Descarte de registros com $P < 0\text{ kW}$ com registro no relatório de validação. |
| 15 | `test_rejeicao_potencia_infinita` | [`src/import_data.py`](../src/import_data.py) | Rejeição de valores `inf` e `-inf` na leitura do CSV. |
| 16 | `test_estatisticas_validacao_mutuamente_exclusivas` | [`src/import_data.py`](../src/import_data.py) | Contabilidade estrita: `total_lidos == validos + descartados`, sem contar uma linha duas vezes se data e potência forem ambas inválidas. |
| 17 | `test_contrato_temporal_minutos_fracionados` | [`src/import_data.py`](../src/import_data.py) | Rejeição de carimbos com minutos ou segundos fracionários (ex: `08:30`). |
| 18 | `test_rejeicao_timestamps_com_fuso_ou_fracoes_segundo` | [`src/import_data.py`](../src/import_data.py) | Rejeição de carimbos com fuso explícito (`+03:00`, `Z`, `UTC`, `GMT`) ou frações de segundo (`.123456`). |
| 19 | `test_deteccao_lacunas_temporais_no_csv` | [`src/import_data.py`](../src/import_data.py) | Identificação e relatório de horas faltantes na série contínua do CSV. |
| 20 | `test_conflito_potencia_mesmo_horario_no_csv` | [`src/import_data.py`](../src/import_data.py) | Disparo imediato de `ValueError` ao encontrar timestamps iguais com potências divergentes no CSV. |
| 21 | `test_reexecucao_idempotente` | [`src/database.py`](../src/database.py) | Reimportação de lote idêntico retorna 0 novos registros sem duplicar dados no SQLite. |
| 22 | `test_reversao_lote_conflitante_sqlite` | [`src/database.py`](../src/database.py) | Transação com `ROLLBACK` total: se uma linha do novo lote conflitar com o banco, nenhuma linha nova é gravada. |
| 23 | `test_conflito_potencia_pequena_diferenca_sqlite` | [`src/database.py`](../src/database.py) | Rejeição de divergências numéricas sutis (ex: `10.00005` vs `10.0`), evitando tolerâncias silenciosas indevidas. |
| 24 | `test_deteccao_lacunas_no_historico_multiplas_importacoes` | [`src/import_data.py`](../src/import_data.py) / [`main.py`](../main.py) | Detecção de lacunas de dias inteiros quando lotes separados são importados sucessivamente no banco. |
| 25 | `test_concordancia_sql_e_pandas_usando_arquivo_queries` | [`sql/queries.sql`](../sql/queries.sql) | Carrega `sql/queries.sql` real, executa no SQLite e valida equivalência exata com Pandas para média, pico, agregações diárias com participação, resumo geral com fator de carga e dia de maior consumo. |
| 26 | `test_pipeline_configuracao_incompativel_antes_da_persistencia` | [`main.py`](../main.py) | Garante interrupção com código `1` antes de criar banco ou persistir dados quando `INTERVALO_HORAS != 1.0` ou tarifa for negativa. |
| 27 | `test_pipeline_deteccao_lacunas_em_importacoes_distintas` | [`main.py`](../main.py) | Garante que o pipeline emite alertas claros no terminal quando lotes separados geram lacunas no histórico consolidado. |
| 28 | `test_pipeline_e2e_com_banco_temporario_e_retorno_falhas` | [`main.py`](../main.py) | Teste ponta a ponta: retorno `0` em sucesso, e retorno `1` em CSV sem dados válidos, falha de exportação ou erro na criação do banco. |
| 29 | `test_cli_argumentos_e_execucao_customizada` | [`main.py`](../main.py) | Validação das opções de CLI com `argparse` (`--csv`, `--tarifa`, `--banco`, `--saida`) e execução do pipeline com parâmetros customizados. |

---

## 3. Execução dos Testes e Relatório de Cobertura

Para executar toda a suíte com verificação de cobertura de código via `pytest-cov`:

```bash
pytest -v --cov=src --cov=main --cov-report=term-missing
```

### Relatório de Cobertura Obtido (v1.0):

| Módulo | Linhas de Código | Linhas Não Cobertas | Cobertura (%) | Escopo Principal |
|---|---|---|---|---|
| [`src/__init__.py`](../src/__init__.py) | 1 | 0 | **100%** | Inicialização do pacote |
| [`src/analysis.py`](../src/analysis.py) | 155 | 9 | **94%** | Motor de cálculo elétrico e síntese |
| [`src/report.py`](../src/report.py) | 123 | 10 | **92%** | Apresentação no terminal e CSV |
| [`src/import_data.py`](../src/import_data.py) | 129 | 17 | **87%** | Ingestão, validação temporal e lacunas |
| [`src/database.py`](../src/database.py) | 59 | 9 | **85%** | Persistência transacional e SQLite |
| [`main.py`](../main.py) | 107 | 25 | **77%** | Orquestração do pipeline e CLI |
| **TOTAL CONSOLIDADO** | **574** | **70** | **88%** | **Suíte completa** |

Resultado da suíte:
```text
============================== 29 passed in 0.36s ==============================
```

### Tolerâncias Numéricas Utilizadas nas Comparações SQL vs. Pandas
Nas verificações de equivalência matemática entre as consultas puras de [`sql/queries.sql`](../sql/queries.sql) e os métodos do Pandas:
- **Potência média, demanda de pico e consumo energético**: tolerância absoluta de $|V_{\text{SQL}} - V_{\text{Pandas}}| \le 0{,}01$;
- **Fator de carga percentual**: tolerância absoluta de $\le 0{,}05\%$, decorrente de arredondamento intermediário em ponto flutuante;
- **Horário do pico e dia de maior consumo**: igualdade estrita de strings alinhadas por data civil.

> **Nota sobre Integração Contínua (CI):**  
> O repositório contém o arquivo de configuração [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) para execução automatizada de testes no GitHub Actions nas versões Python 3.10 a 3.13. No entanto, a execução remota nos servidores do GitHub não foi atestada nesta sessão local e dependerá da publicação do repositório.

---

## 4. Análise de Cobertura e Limitações Conhecidas

### Comportamentos Verificados:
- Consistência dimensional dos cálculos de engenharia elétrica (potência média, demanda máxima, integral de energia, fator de carga e participação diária);
- Contrato temporal estrito (início de hora cheia, sem fuso explícito nem frações de segundo);
- Transações com `ROLLBACK` integral em conflito de dados e idempotência em reimportações;
- Auditoria de cobertura e detecção de lacunas tanto no lote importado quanto no histórico consolidado do banco;
- Equivalência matemática entre todas as consultas de `sql/queries.sql` e as funções do Pandas;
- Códigos de saída do processo (`0` e `1`) em falhas controladas antes e depois da persistência.

### Lacunas e Melhorias Futuras:
1. **Testes de Volume**: O conjunto de dados atual possui 168 medições. Não há testes de estresse com milhões de linhas para avaliar o consumo de memória RAM do Pandas.
2. **Resoluções Sub-horárias**: O contrato da v1 rejeita medições em 15 ou 30 minutos. O suporte a agregação temporal prévia é um objetivo para a v2.0.
3. **Múltiplos Formatos de Entrada**: O sistema suporta apenas CSV separado por vírgula. Formatos com ponto e vírgula ou Parquet não são suportados na v1.
