# Guia de Estudo e Preparação Técnica: PowerMonitor

> **Público-alvo:** Engenheiros Eletricistas consolidando conhecimentos em Python, Pandas e SQL, preparando-se para entrevistas de emprego e apresentações técnicas de projetos.

---

## Sumário

1. [Visão Geral e Mentalidade de Engenharia](#1-visão-geral-e-mentalidade-de-engenharia)
2. [Roteiro Estruturado de Estudo em 8 Etapas](#2-roteiro-estruturado-de-estudo-em-8-etapas)
3. [Exemplo Passo a Passo: Rastreamento Completo de 2 Medições](#3-exemplo-passo-a-passo-rastreamento-completo-de-2-medições)
4. [Matriz de Previsão de Falhas e Casos de Borda](#4-matriz-de-previsão-de-falhas-e-casos-de-borda)
5. [Roteiro de Apresentação de 5 Minutos (Pitch Técnico)](#5-roteiro-de-apresentação-de-5-minutos-pitch-técnico)
6. [Perguntas e Respostas Prováveis em Entrevistas](#6-perguntas-e-respostas-prováveis-em-entrevistas)
7. [Checklist de Autoavaliação](#7-checklist-de-autoavaliação)

---

## 1. Visão Geral e Mentalidade de Engenharia

O **PowerMonitor** foi concebido como um pipeline de telemetria e análise de consumo elétrico que une o **rigor da Engenharia Elétrica** às **boas práticas de Engenharia de Software**:

* **Não mascarar anomalias de campo:** Na engenharia física, dado ausente ou corrompido nunca deve ser preenchido artificialmente por zero nem interpolado sem aviso prévio. Faltas de energia geram lacunas de medição que afetam diretamente o fator de carga e a apuração da fatura.
* **Separação de responsabilidades (SoC):** Cada módulo possui uma única missão (configuração, persistência, saneamento, cálculo puro ou apresentação).
* **Funções puras e testabilidade:** O cálculo de energia e demanda é matematicamente isolado de operações de entrada/saída (I/O). Isso permite simulações determinísticas e testes unitários automatizados.

```mermaid
flowchart LR
    A["CSV de Campo\n(Registradores)"] --> B["Ingestão & Saneamento\n(Pandas / Regex)"]
    B --> C["Persistência ACID\n(SQLite)"]
    C --> D["Análise & Agregação\n(Funções Puras)"]
    D --> E["Relatório de Terminal\n& Exportação CSV"]
```

---

## 2. Roteiro Estruturado de Estudo em 8 Etapas

### Etapa 1: Configuração e Constantes de Domínio

* **Arquivo para ler:** [`config.py`](file:///Users/elydocarmobarros/Projects/power-monitor/config.py)
* **Conceito de Programação vs Elétrica:**
  * *Software:* Constantes em caixa alta (PEP 8) e uso do módulo `pathlib.Path` para resolução robusta de caminhos independentemente do sistema operacional (Windows vs Linux/Mac).
  * *Elétrica:* O parâmetro `INTERVALO_HORAS` ($\Delta t$) define a base de tempo da integração numérica $E = \int P(t)\,dt$. Modificar $\Delta t$ de $1{,}0\text{ h}$ para $0{,}25\text{ h}$ (15 minutos) altera a escala dimensional do cálculo de energia.
* **Pergunta de Verificação:** Por que caminhos de arquivos e parâmetros de medição nunca devem ser digitados diretamente ("hardcoded") dentro das funções de cálculo?
  * *Resposta esperada:* Para desacoplar a lógica matemática da infraestrutura local, permitindo rodar simulações com múltiplos arquivos sem modificar o código.
* **Exercício Prático:**
  Abra um terminal interativo Python e execute:
  ```python
  import config
  print("Caminho do banco:", config.DATABASE_PATH.name)
  print("Tarifa configurada: R$", config.TARIFA_KWH, "/ kWh")
  print("Passo de integração:", config.INTERVALO_HORAS, "hora(s)")
  ```
  *Resultado esperado:* Ver os parâmetros padrão centralizados sem erros de importação.

---

### Etapa 2: Modelagem Relacional e Integridade de Dados

* **Arquivos para ler:** [`sql/schema.sql`](file:///Users/elydocarmobarros/Projects/power-monitor/sql/schema.sql) e [`src/database.py`](file:///Users/elydocarmobarros/Projects/power-monitor/src/database.py)
* **Conceito de Programação vs Elétrica:**
  * *Software:* Bancos relacionais (SQL), transações ACID, restrições `UNIQUE`, consultas parametrizadas (`?`) contra SQL Injection e gerenciador de contexto `with conn`.
  * *Elétrica:* Um medidor instalado em um alimentador não pode registrar dois consumos de potência ativa distintos no mesmíssimo intervalo temporal. A chave primária `UNIQUE(data_hora)` no SQLite atua como uma proteção física contra duplicatas de telemetria.
* **Pergunta de Verificação:** Qual a diferença entre usar `with conn:` e `conn.close()` no SQLite?
  * *Resposta esperada:* O `with conn:` gerencia a **transação** (executa `COMMIT` se der certo ou `ROLLBACK` se houver erro), enquanto `conn.close()` encerra a **conexão física** com o arquivo do banco no disco.
* **Exercício Prático:**
  Execute o script abaixo para criar um banco em memória e tentar inserir uma medição duplicada com valor conflitante:
  ```python
  import sqlite3
  from src.database import create_tables, insert_medicoes
  import pandas as pd

  conn = sqlite3.connect(":memory:")
  create_tables(conn)
  df1 = pd.DataFrame([{"data_hora": "2026-08-01 08:00", "potencia_kw": 10.0}])
  insert_medicoes(conn, df1)

  # Tentativa com valor conflitante na mesma hora
  df2 = pd.DataFrame([{"data_hora": "2026-08-01 08:00", "potencia_kw": 99.0}])
  try:
      insert_medicoes(conn, df2)
  except ValueError as e:
      print("Sucesso! O banco barrou a inconsistência:", e)
  ```
  *Resultado esperado:* Exibição da mensagem de erro indicando conflito de valores na data/hora existente.

---

### Etapa 3: Ingestão, Validação e Saneamento de Dados

* **Arquivo para ler:** [`src/import_data.py`](file:///Users/elydocarmobarros/Projects/power-monitor/src/import_data.py)
* **Conceito de Programação vs Elétrica:**
  * *Software:* Princípio "Garbage In, Garbage Out" (GIGO), expressões regulares (Regex), validação de tipos e contabilidade estrita de linhas descartadas.
  * *Elétrica:* Potência ativa em regime de consumidor passivo deve ser estritamente $\ge 0$. Valores negativos indicam erro de inversão de polaridade dos TCs (Transformadores de Corrente) ou injeção de geração própria não cadastrada. O alinhamento na grade temporal (`minuto % 60 == 0`) garante que as medições respeitam os intervalos regulatórios.
* **Pergunta de Verificação:** Se um registrador de energia desligar das 14:00 às 18:00, por que o sistema não preenche essas 4 horas com zero ($0\text{ kW}$)?
  * *Resposta esperada:* Porque preencher com zero falsifica a potência média (puxando-a para baixo) e distorce o Fator de Carga. Em metrologia elétrica, ausência de medição $\neq$ consumo nulo.
* **Exercício Prático:**
  Valide um registro com formato de texto e número em string com vírgula:
  ```python
  from src.import_data import extrair_potencia_float
  print(extrair_potencia_float("15,75 kW"))
  print(extrair_potencia_float("-2.5"))  # Deve retornar None (negativo)
  ```
  *Resultado esperado:* `15.75` e `None`.

---

### Etapa 4: Análise Estatística e Agregações com Pandas

* **Arquivo para ler:** [`src/analysis.py`](file:///Users/elydocarmobarros/Projects/power-monitor/src/analysis.py) (funções de média, demanda máxima e consumo diário)
* **Conceito de Programação vs Elétrica:**
  * *Software:* Operações vetorizadas (`.mean()`, `.max()`), agrupamento relacional em memória (`.groupby('dia')`) e agregações múltiplas com `.agg()`.
  * *Elétrica:* A potência média $\bar{P}$ é a média aritmética simples das amostras horárias. A demanda máxima horária representa o maior valor de potência ativa integrado em uma janela de 60 minutos, crucial para dimensionamento de transformadores e cabos.
* **Pergunta de Verificação:** Se houver empate no valor da demanda máxima em dois horários distintos, como o algoritmo decide qual registrar?
  * *Resposta esperada:* O código aplica ordenação determinística de desempate: `.sort_values(["potencia_kw", "data_hora"], ascending=[False, True])`, elegendo rigorosamente a primeira ocorrência cronológica.
* **Exercício Prático:**
  Calcule a agregação diária de 3 medições com Pandas:
  ```python
  import pandas as pd
  from src.analysis import calcular_consumo_diario

  df = pd.DataFrame([
      {"data_hora": "2026-08-01 08:00", "potencia_kw": 10.0},
      {"data_hora": "2026-08-01 09:00", "potencia_kw": 20.0},
      {"data_hora": "2026-08-02 10:00", "potencia_kw": 15.0}
  ])
  df_diario = calcular_consumo_diario(df, intervalo_horas=1.0)
  print(df_diario[["dia", "total_medicoes", "consumo_kwh", "participacao_percentual"]])
  ```
  *Resultado esperado:* Duas linhas (dias `2026-08-01` com $30{,}0\text{ kWh}$ e `2026-08-02` com $15{,}0\text{ kWh}$), com participações de $66{,}67\%$ e $33{,}33\%$.

---

### Etapa 5: Indicadores Avançados e Métricas Elétricas

* **Arquivo para ler:** [`src/analysis.py`](file:///Users/elydocarmobarros/Projects/power-monitor/src/analysis.py) (fator de carga, cobertura e síntese executiva)
* **Conceito de Programação vs Elétrica:**
  * *Software:* Tipagem estruturada com `TypedDict`, contratos explícitos de dados e geração de texto executivo determinístico sem alucinações.
  * *Elétrica:* O **Fator de Carga ($FC$)**:
    $$FC = \frac{P_{\text{média}}}{D_{\text{máxima}}} = \frac{\text{Energia total}}{D_{\text{máxima}} \times T}$$
    $FC$ quantifica a uniformidade e o perfil de utilização da instalação elétrica em relação à sua capacidade de pico. $FC$ baixo (ex: $0{,}35$) indica perfil com picos concentrados e capacidade ociosa na maior parte do dia; $FC$ alto (ex: $0{,}85$) indica perfil achatado e uso contínuo da infraestrutura. **$FC$ não mede eficiência ou rendimento de máquinas**.
* **Pergunta de Verificação:** Se a demanda máxima de uma instalação for $0\text{ kW}$ (ex: circuito desativado), o que o Fator de Carga deve retornar?
  * *Resposta esperada:* `None` (Não Aplicável). Dividir por zero geraria erro ou infinito (`inf`), o que é fisicamente incoerente.
* **Exercício Prático:**
  Calcule o fator de carga:
  ```python
  from src.analysis import calcular_fator_carga
  print("FC normal:", calcular_fator_carga(potencia_media=15.0, demanda_maxima=20.0))
  print("FC com demanda zero:", calcular_fator_carga(potencia_media=0.0, demanda_maxima=0.0))
  ```
  *Resultado esperado:* `0.75` e `None`.

---

### Etapa 6: Apresentação e Exportação de Resultados

* **Arquivo para ler:** [`src/report.py`](file:///Users/elydocarmobarros/Projects/power-monitor/src/report.py)
* **Conceito de Programação vs Elétrica:**
  * *Software:* Formatação de strings (`f-strings`) com alinhamento tabular fixo, substituição segura de caracteres decimais sem colisões e tratamento de exceções de I/O (`RuntimeError ... from e`).
  * *Elétrica:* Exibição de laudo técnico claro com notas de rodapé metrológicas (diferenciação entre demanda horária integrada e demanda contratada em fatura).
* **Pergunta de Verificação:** Na função `formatar_numero_br`, por que se utiliza um caractere temporário `'X'` ao substituir pontos e vírgulas?
  * *Resposta esperada:* Para evitar a colisão de caracteres. Se substituíssemos `.` por `,` e em seguida `,` por `.`, todos os dígitos separadores se tornariam idênticos.
* **Exercício Prático:**
  Teste a formatação brasileira:
  ```python
  from src.report import formatar_numero_br
  print(formatar_numero_br(1254320.756, casas_decimais=2))
  ```
  *Resultado esperado:* `"1.254.320,76"`.

---

### Etapa 7: Orquestração e Interface de Linha de Comando

* **Arquivo para ler:** [`main.py`](file:///Users/elydocarmobarros/Projects/power-monitor/main.py)
* **Conceito de Programação vs Elétrica:**
  * *Software:* Padrão Orquestrador/Maestro, parsing de argumentos CLI com `argparse`, códigos de saída do processo (`sys.exit(0)` ou `sys.exit(1)`).
  * *Elétrica:* Equivalente a um relé digital com painel de parametrização: permite ao operador redefinir a tarifa, o caminho do arquivo e a base de tempo sem precisar soldar novos componentes ou reprogramar o microcontrolador.
* **Pergunta de Verificação:** Por que `main.py` retorna `1` quando um arquivo CSV não existe ou possui linhas inválidas?
  * *Resposta esperada:* Para permitir que sistemas de agendamento (Cron, Airflow) ou pipelines de integração contínua (CI) identifiquem a falha e acionem alertas operacionais.
* **Exercício Prático:**
  Exiba o menu de ajuda do pipeline:
  ```bash
  python3 main.py --help
  ```
  *Resultado esperado:* Visualizar a descrição formal de todas as flags (`--csv`, `--tarifa`, `--banco`, `--saida`, `--intervalo`).

---

### Etapa 8: Qualidade de Software, Testes e CI/CD

* **Arquivos para ler:** [`tests/test_analysis.py`](file:///Users/elydocarmobarros/Projects/power-monitor/tests/test_analysis.py), [`tests/test_database.py`](file:///Users/elydocarmobarros/Projects/power-monitor/tests/test_database.py), [`pytest.ini`](file:///Users/elydocarmobarros/Projects/power-monitor/pytest.ini) e [`.github/workflows/ci.yml`](file:///Users/elydocarmobarros/Projects/power-monitor/.github/workflows/ci.yml)
* **Conceito de Programação vs Elétrica:**
  * *Software:* Testes unitários com `pytest`, fixtures de banco em memória, asserções de contabilidade metrológica (`assert total_lidos == validos + descartados`), cobertura de código (`pytest-cov`) e automação com GitHub Actions.
  * *Elétrica:* Ensaios de tipo e testes de bancada de instrumentos de medição: submeter o algoritmo a condições de curto-circuito lógico (dados vazios, negativos, nulos) para comprovar sua imunidade e precisão antes de colocá-lo em operação na subestação.
* **Pergunta de Verificação:** O que significa a "Asserção de Identidade" nos testes de importação?
  * *Resposta esperada:* Comprova que $N_{\text{lidos}} = N_{\text{válidos}} + N_{\text{descartados}}$ e que a soma de todos os descartes categorizados bate exatamente com o total descartado.
* **Exercício Prático:**
  Rode a suíte de testes com cobertura:
  ```bash
  pytest -v --cov=src --cov=main
  ```
  *Resultado esperado:* 36 testes passando com $100\%$ de sucesso e cobertura $\ge 89\%$.

---

## 3. Exemplo Passo a Passo: Rastreamento Completo de 2 Medições

Para dominar a dinâmica interna do sistema, acompanhe a trajetória exata de um lote mínimo com **duas medições horárias**:

### Dados de Entrada (`teste_simples.csv`)
```csv
data_hora,potencia_kw
2026-08-01 08:00,10
2026-08-01 09:00,20
```

### Parâmetros de Simulação
* $\Delta t = 1{,}0\text{ h}$ (`--intervalo 1.0`)
* Tarifa = $\text{R\$}~0{,}75/\text{kWh}$ (`--tarifa 0.75`)

---

### Passo 1: Leitura e Saneamento (`src/import_data.py`)
1. **Verificação de Cabeçalho:** As colunas `data_hora` e `potencia_kw` estão presentes.
2. **Validação das Linhas:**
   * Linha 1: `2026-08-01 08:00` casa com o regex `^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$`. Minuto é `00`, perfeitamente divisível por 60. Potência `10` é convertida para float `10.0` ($\ge 0$). Válida!
   * Linha 2: `2026-08-01 09:00`. Minuto `00`. Potência `20.0` ($\ge 0$). Válida!
3. **Contabilidade Metrológica:**
   * $\text{Total lidos} = 2$
   * $\text{Registros válidos} = 2$
   * $\text{Linhas descartadas} = 0$
   * $\text{Identidade auditada:}~2 = 2 + 0$ (OK!)

---

### Passo 2: Persistência no Banco SQLite (`src/database.py`)
1. A tabela `medicoes` recebe os dados via comando SQL parametrizado:
   ```sql
   INSERT INTO medicoes (data_hora, potencia_kw) VALUES (?, ?);
   ```
2. O banco persiste em ordem cronológica com chave primária única:
   * `('2026-08-01 08:00', 10.0)`
   * `('2026-08-01 09:00', 20.0)`
3. A transação finaliza com sucesso (`novos_inseridos = 2`).

---

### Passo 3: Consulta e Carregamento no Pandas (`src/database.py`)
O sistema executa:
```sql
SELECT data_hora, potencia_kw FROM medicoes ORDER BY data_hora ASC;
```
Resultando em um DataFrame Pandas de 2 linhas:
* Índice 0: `2026-08-01 08:00:00`, `10.0`
* Índice 1: `2026-08-01 09:00:00`, `20.0`

---

### Passo 4: Cálculos Técnicos de Engenharia Elétrica (`src/analysis.py`)

#### A. Potência Média ($\bar{P}$)
$$\bar{P} = \frac{1}{N} \sum_{i=1}^{N} P_i = \frac{10{,}0 + 20{,}0}{2} = 15{,}00\text{ kW}$$

#### B. Demanda Máxima Horária de Pico ($\hat{D}$) e Horário
* O maior valor do vetor de potência é $20{,}00\text{ kW}$.
* O carimbo associado é `2026-08-01 09:00`.
* *Interpretação:* Representa a potência média integrada no intervalo entre 09:00 e 10:00.

#### C. Energia Total Consumida ($E$)
Como o intervalo é de 1 hora ($\Delta t = 1{,}0\text{ h}$):
$$E = \sum (P_i \times \Delta t) = (10{,}0 \times 1{,}0) + (20{,}0 \times 1{,}0) = 10{,}0 + 20{,}0 = 30{,}00\text{ kWh}$$

#### D. Custo Financeiro Estimado ($C$)
$$C = E \times \text{Tarifa} = 30{,}00\text{ kWh} \times \text{R\$}~0{,}75/\text{kWh} = \text{R\$}~22{,}50$$

#### E. Fator de Carga ($FC$)
$$FC = \frac{\bar{P}}{\hat{D}} = \frac{15{,}00}{20{,}00} = 0{,}75 \implies 75{,}00\%$$
* *Interpretação:* Durante o período medido, a demanda média ocupou $75\%$ do pico observado, indicando moderada uniformidade de carga.

#### F. Cobertura Temporal de Medições
* Primeira medição: `2026-08-01 08:00`
* Última medição: `2026-08-01 09:00`
* Janela temporal: 1 hora decorrida $\implies$ Passos esperados com $\Delta t = 1\text{h}$: $2$ (às 08:00 e às 09:00).
* Horas medidas: $2$. Horas ausentes: $0$.
* Cobertura no intervalo monitorado: $\frac{2}{2} \times 100\% = 100{,}0\%$.

#### G. Agregação Diária (`df_diario`)
* Data: `2026-08-01`
* Total de medições: $2$
* Classificação: **Dia Parcial** ($2\text{ de }24\text{ horas}$, portanto `dia_completo = False`).
* Consumo do dia: $30{,}00\text{ kWh}$.
* Participação do dia na fatura: $\frac{30{,}00}{30{,}00} \times 100\% = 100{,}00\%$.

---

### Passo 5: Exibição e Exportação (`src/report.py`)
O relatório no terminal exibe:
```text
============================================================================
                      P O W E R M O N I T O R                       
       Análise de Consumo e Demanda de Energia Elétrica (v1.0)       
============================================================================

[FLUXO DA EXECUÇÃO ATUAL]
Linhas lidas no CSV:           2
Medições válidas no lote:      2
Linhas descartadas:            0
Novas medições inseridas:      2

[HISTÓRICO CONSOLIDADO NO BANCO SQLITE]
Total de medições no histórico: 2
Período temporal coberto:       01/08/2026 a 01/08/2026
Cobertura temporal:             2 de 2 horas esperadas (100,0%)

Potência média horária:
  15,00 kW

Maior potência média horária (demanda de pico):
  20,00 kW
Horário da ocorrência de pico:
  2026-08-01 09:00

Fator de carga da instalação:
  75,00%
  (relação potência média / pico; indica uniformidade, não eficiência)

Energia consumida estimada no período:
  30,00 kWh
Dia de maior consumo registrado:
  01/08/2026 (30,00 kWh (cobertura parcial))

Custo financeiro estimado (simulação simplificada):
  R$ 22,50 (tarifa de referência: R$ 0,75/kWh)
```

E o arquivo CSV gerado em `output/relatorio_diario.csv` contém:
```csv
dia,total_medicoes,dia_completo,potencia_media_kw,demanda_maxima_kw,consumo_kwh,participacao_percentual,tarifa_aplicada_r_kwh,custo_estimado_dia_r
2026-08-01,2,False,15.0,20.0,30.0,100.0,0.75,22.5
```

---

## 4. Matriz de Previsão de Falhas e Casos de Borda

Conhecer como o software reage diante de falhas é essencial para demonstrar maturidade técnica em entrevistas:

| Cenário de Erro / Anomalia | Módulo Responsável | Mecanismo de Detecção | Comportamento do Sistema | Comando CLI de Teste Isolado |
|---|---|---|---|---|
| **Arquivo CSV inexistente** | `import_data.py` | `if not path.exists(): raise FileNotFoundError` | Aborta com mensagem de erro amigável; exit code 1. | `python3 main.py --csv /tmp/inexistente.csv --banco /tmp/t1.db` |
| **Cabeçalho ausente/errado** (ex: `hora,kw`) | `import_data.py` | Checagem de conjunto de colunas obrigatórias | Lança `ValueError` indicando as colunas faltantes; exit code 1. | `echo "hora,kw\n2026-08-01 08:00,10" > /tmp/cab.csv && python3 main.py --csv /tmp/cab.csv --banco /tmp/t2.db` |
| **Potência ativa negativa** (ex: `-15.0`) | `import_data.py` | Validação de domínio físico: `potencia < 0` | Descarta a linha, incrementa contador de descartes e emite aviso explicativo. | `echo "data_hora,potencia_kw\n2026-08-01 08:00,-15" > /tmp/neg.csv && python3 main.py --csv /tmp/neg.csv --banco /tmp/t3.db` |
| **Formato de data corrompido** (ex: `01/08/2026 08:00`) | `import_data.py` | Regex estrito `^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$` | Descarta a linha (evita ambiguidade entre dia e mês); emite aviso. | `echo "data_hora,potencia_kw\n01/08/2026 08:00,10" > /tmp/fmt.csv && python3 main.py --csv /tmp/fmt.csv --banco /tmp/t4.db` |
| **Medição desalinhada da grade** (ex: `08:17` em base 1h) | `import_data.py` | Aritmética modular: `dt.minute % 60 != 0` | Descarta a linha por desalinhamento com o passo configurado. | `echo "data_hora,potencia_kw\n2026-08-01 08:17,10" > /tmp/grid.csv && python3 main.py --csv /tmp/grid.csv --banco /tmp/t5.db` |
| **Reimportação da mesma medição idêntica** | `database.py` | Consulta idempotente: `SELECT COUNT(*)` antes do insert | Reconhece o dado já existente; não duplica e não gera erro. | `echo "data_hora,potencia_kw\n2026-08-01 08:00,10" > /tmp/dup.csv && python3 main.py --csv /tmp/dup.csv --banco /tmp/t6.db && python3 main.py --csv /tmp/dup.csv --banco /tmp/t6.db` |
| **Duplicata conflitante** (mesma hora, potência diferente) | `database.py` | Validação de consistência do banco | Aborta a transação com `ROLLBACK` e lança `ValueError`. Preserva a integridade do banco. | `echo "data_hora,potencia_kw\n2026-08-01 08:00,10" > /tmp/c1.csv && python3 main.py --csv /tmp/c1.csv --banco /tmp/t7.db && echo "data_hora,potencia_kw\n2026-08-01 08:00,99" > /tmp/c2.csv && python3 main.py --csv /tmp/c2.csv --banco /tmp/t7.db` |
| **Intervalo não suportado** (ex: `--intervalo 0.75`) | `main.py` / `analysis.py` | `validar_intervalo_horas` (`0.25, 0.5, 1.0`) | Rejeita o parâmetro logo na inicialização (Fail-Fast); exit code 1. | `python3 main.py --intervalo 0.75 --banco /tmp/t8.db` |

> **Nota:** Todos os comandos de teste utilizam caminhos em `/tmp/` para não alterar os dados reais da pasta `data/` ou o banco `database/power_monitor.db`.

---

## 5. Roteiro de Apresentação de 5 Minutos (Pitch Técnico)

Use este roteiro estruturado quando pedirem para você apresentar o projeto em uma entrevista técnica:

### Minuto 1: Contexto e Oportunidade
> *"Como Engenheiro Eletricista com foco em dados e software, desenvolvi o **PowerMonitor** para resolver uma dor crítica que presenciei na gestão de energia: a desconexão entre os arquivos brutos gerados por registradores de grandezas elétricas e a tomada de decisão gerencial.*
>
> *Na prática, arquivos CSV de campo chegam corrompidos, com ruídos de comunicação, registros negativos por inversão de TCs e lacunas causadas por quedas de energia. Planilhas manuais costumam preencher essas lacunas com zero ou sobrescrever dados sem controle, gerando distorções perigosas em auditorias e faturamento.*
>
> *O PowerMonitor é um pipeline automatizado que ingere esses arquivos brutos, aplica saneamento com regras elétricas rigorosas, armazena o histórico em banco relacional e calcula indicadores técnicos como demanda máxima, consumo acumulado e fator de carga."*

### Minuto 2: Arquitetura e Decisões de Software
> *"Para garantir confiabilidade, estruturei o projeto seguindo o princípio da Separação de Responsabilidades (SoC) em camadas:*
>
> *1. **Ingestão e Validação:** Utilizo Pandas e expressões regulares para filtrar ruídos antes de qualquer processamento.*
> *2. **Persistência Relacional:** Optei pelo SQLite com integridade transacional (ACID). A chave primária única por carimbo temporal impede que medições duplicadas inflacionem o consumo, e transações garantem que ou o lote inteiro é consistente ou nada é gravado.*
> *3. **Cálculo Analítico Puro:** O módulo de análise é composto exclusivamente por funções puras — sem efeitos colaterais ou I/O. Isso facilita testes unitários determinísticos.*
> *4. **Apresentação:** Relatórios de terminal alinhados e exportação diária em CSV para integração com PowerBI ou Excel."*

### Minuto 3: Tratamento de Qualidade de Dados (Metrologia Elétrica)
> *"Um diferencial técnico deste projeto é a fidelidade aos princípios da metrologia elétrica:*
>
> *Primeiro: **Nunca assumimos que dado ausente é consumo zero**. Se o registrador ficou sem alimentação das 14h às 18h, o sistema detecta a lacuna temporal via aritmética de séries e avisa o operador. Preencher com zero reduziria artificialmente a potência média e adulteraria o Fator de Carga.*
>
> *Segundo: **Auditoria estrita de linhas**. Cada execução do pipeline valida uma identidade matemática: `Linhas lidas = Registros válidos + Linhas descartadas`. Se uma linha for descartada por valor negativo ou carimbo fora da grade de 15, 30 ou 60 minutos, ela é categorizada e contabilizada explicitamente."*

### Minuto 4: Métricas Elétricas e Interpretação Físico-Operacional
> *"Nos indicadores calculados, tivemos o cuidado de traduzir a física da operação:*
>
> *A **Demanda Máxima** é calculada como a maior potência média integrada no intervalo, registrando com precisão o horário do evento para posterior investigação operacional.*
>
> *O **Fator de Carga** é tratado com o devido rigor: ele expressa a modulação da curva de carga e a taxa de utilização da infraestrutura elétrica frente ao pico, e **não** a eficiência dos motores ou aparelhos da fábrica.*
>
> *Além disso, identificamos explicitamente **dias parciais**: se um dia possui apenas 10 medições em vez de 24, o relatório alerta que aquele consumo não pode ser comparado diretamente a um dia cheio."*

### Minuto 5: Confiabilidade, Testes e Escalabilidade
> *"Por fim, apliquei práticas profissionais de qualidade de software:*
>
> *O projeto conta com **36 testes automatizados com pytest**, cobrindo validações de entrada, transações SQL, cálculos estatísticos e integridade de pipeline, atingindo **89% de cobertura de código**.*
>
> *Configurei um pipeline de **CI (Integração Contínua) no GitHub Actions**, que executa todos os testes a cada push ou pull request em ambiente limpo Linux.*
>
> *A arquitetura foi desenhada para evoluir facilmente: podemos plugar tarifas horossazonais (ponta/fora de ponta da Resolução 1.000 da ANEEL) ou trocar o SQLite por PostgreSQL sem alterar as fórmulas do módulo analítico."*

---

## 6. Perguntas e Respostas Prováveis em Entrevistas

### P1: "Por que você usou SQLite em vez de manipular tudo diretamente em arquivos CSV ou no Pandas?"
**Resposta Recomendada:**
> *"Arquivos CSV não oferecem garantias transacionais (ACID). Se o script falhar no meio da escrita de um CSV, o arquivo pode ser corrompido ou ficar incompleto. Além disso, o SQLite nos dá a restrição `UNIQUE(data_hora)`, impedindo duplicatas de medição de forma nativa e atômica. O Pandas é excelente para manipulação e agregações em memória RAM, mas a persistência histórica de longo prazo pertence a um banco relacional estruturado."*

### P2: "Por que você calculou o consumo como `potencia_kw * intervalo_horas` em vez de apenas somar a coluna de potência?"
**Resposta Recomendada:**
> *"Porque potência ativa é uma taxa de fluxo instantâneo em quilowatts (kW), enquanto energia é a integral da potência no tempo em quilowatts-hora (kWh): $E = \int P(t)\,dt$. A soma direta dos valores numéricos só equivaleria a kWh se o intervalo de amostragem fosse exatamente de 1 hora ($\Delta t = 1{,}0\text{ h}$). Ao multiplicar explicitamente por `intervalo_horas`, o código suporta nativamente medições de 15 minutos ($\Delta t = 0{,}25\text{ h}$) ou 30 minutos ($\Delta t = 0{,}5\text{ h}$), mantendo a coerência dimensional da física."*

### P3: "O que acontece se o medidor ficar sem energia ou sem sinal por 5 horas? Como seu pipeline lida com isso?"
**Resposta Recomendada:**
> *"O pipeline utiliza a função `identificar_lacunas_temporais`, que gera o índice temporal esperado completo com `pd.date_range` e compara com as datas reais via `DatetimeIndex.difference`. O sistema identifica exatamente quais horas faltaram e exibe um alerta de qualidade. Importante: nós **não** preenchemos essas horas com zero nem interpolamos valores, pois isso distorceria a potência média e o fator de carga. O relatório calcula as métricas estritamente sobre as horas medidas e indica a taxa de cobertura temporal."*

### P4: "Se uma indústria apresentar Fator de Carga de 0,40, podemos afirmar que as máquinas dela são energeticamente ineficientes?"
**Resposta Recomendada:**
> *"Não. Essa é uma confusão comum entre **uniformidade de curva de carga** e **rendimento eletromecânico**. Um fator de carga de 0,40 (ou 40%) significa apenas que a potência média foi 40% do pico de demanda registrado no período — por exemplo, uma fábrica que opera em apenas um turno diário de 8 horas e desliga à noite. Os motores podem ter selo Procel A de altíssima eficiência; o FC baixo reflete o perfil operacional e a ociosidade da demanda contratada, não o desperdício intrínseco dos equipamentos."*

### P5: "Como o sistema reage se o registrador reenviar as mesmas medições no dia seguinte?"
**Resposta Recomendada:**
> *"O sistema é idempotente: antes de tentar inserir, a função `insert_medicoes` verifica se a chave `data_hora` já existe no banco. Se já existir com o mesmo valor de potência, o registro é ignorado silenciosamente (`novos_inseridos = 0`), sem erro. Porém, se a data/hora já existir com um valor de potência diferente, a função aborta com `ROLLBACK` e lança um `ValueError`, alertando sobre a inconsistência dos dados para proteger o histórico."*

### P6: "Por que você isolou o módulo `analysis.py` como funções puras sem operações de banco ou disco?"
**Resposta Recomendada:**
> *"Funções puras dependem exclusivamente de seus argumentos de entrada e retornam saídas previsíveis, sem modificar o ambiente externo ('side effects'). Isso torna os testes unitários extremamente rápidos, baratos e determinísticos: podemos injetar pequenos DataFrames artificiais criados em memória e testar todas as condições de contorno (listas vazias, valores nulos, empates de demanda) sem depender de conexões com disco ou arquivos físicos."*

### P7: "Qual a diferença entre a Demanda Máxima apurada no seu projeto e a Demanda Contratada na fatura da concessionária?"
**Resposta Recomendada:**
> *"A Demanda Máxima apurada no projeto é a maior potência média observada nas amostras do histórico analisado. A Demanda Contratada, por sua vez, é um valor contratual fixo em kW acordado previamente entre o consumidor do Grupo A e a distribuidora de energia elétrica (conforme regras da ANEEL). Se a demanda máxima medida ultrapassar a contratada em mais de 5%, a unidade sofre cobrança de ultrapassagem tarifária. O PowerMonitor fornece a visibilidade do pico medido exatamente para subsidiar a gestão e ajuste dessa demanda contratada."*

---

## 7. Checklist de Autoavaliação

Antes de participar de uma entrevista técnica, certifique-se de que consegue marcar todas as caixas abaixo:

- [ ] **Conceitos Elétricos:**
  - [ ] Sei explicar a diferença dimensional e física entre kW (potência) e kWh (energia).
  - [ ] Sei calcular o Fator de Carga manualmente e explicar sua implicação operacional.
  - [ ] Compreendo por que a falta de energia gera lacunas e por que não devemos preenchê-las com zero.
  - [ ] Sei a diferença entre demanda média horária integrada e demanda instantânea de partida de motor.

- [ ] **Python e Pandas:**
  - [ ] Compreendo a importância de `df.copy()` para evitar efeitos colaterais em memória.
  - [ ] Sei explicar como o `.groupby('dia').agg(...)` funciona para agregar séries temporais.
  - [ ] Sei como `argparse` gerencia parâmetros de linha de comando com valores padrão de `config.py`.
  - [ ] Sei por que usamos `pathlib.Path` em vez de manipulação manual de strings de caminhos.

- [ ] **SQL e Persistência:**
  - [ ] Sei explicar o papel da chave primária `UNIQUE(data_hora)` no SQLite.
  - [ ] Sei a diferença entre consultas parametrizadas com `?` e concatenação insegura de strings.
  - [ ] Compreendo o papel do gerenciador de transações (`COMMIT` e `ROLLBACK`).

- [ ] **Qualidade de Software:**
  - [ ] Consigo rodar a suíte de testes (`pytest`) e explicar como a cobertura de código é calculada.
  - [ ] Sei descrever a Asserção de Identidade: $\text{Total} = \text{Válidos} + \text{Descartados}$.
  - [ ] Consigo navegar com segurança pelos 5 módulos da pasta `src/` e demonstrar onde cada cálculo é feito.
