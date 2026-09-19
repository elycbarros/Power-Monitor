# Dados e Metodologia de Cálculo

Este documento detalha o dicionário de dados, as grandezas físicas, o contrato temporal, a formulação matemática e os procedimentos de validação do **PowerMonitor (v1.0)**.

---

## 1. Dicionário de Dados

### 1.1 Arquivo de Entrada (`data/medicoes.csv`)

| Campo | Tipo | Unidade | Descrição e Restrições |
|---|---|---|---|
| `data_hora` | Texto | N/A | Carimbo de data e hora no formato `YYYY-MM-DD HH:MM`. Deve representar o **início exato de uma hora cheia** (minuto, segundo e fração zero). Não são aceitos fusos horários explícitos (ex: `+03:00` ou `Z`) nem frações de segundo. |
| `potencia_kw` | Numérico (`float`) | kW | Potência ativa média demandada durante o intervalo horário de 1 hora subsequente. Deve ser um número finito e não negativo ($P \ge 0$). |

### 1.2 Tabela Relacional (`medicoes` no SQLite)

| Coluna | Tipo SQLite | Restrições | Descrição |
|---|---|---|---|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Identificador sequencial único do registro. |
| `data_hora` | `DATETIME` | `NOT NULL UNIQUE` | Timestamp da medição em texto ISO 8601 (`YYYY-MM-DD HH:MM:SS`). |
| `potencia_kw` | `REAL` | `NOT NULL` | Potência ativa média em quilowatts (kW). |

### 1.3 Arquivo de Relatório Exportado (`output/relatorio.csv`)
*(Arquivo local gerado após a execução, listado no `.gitignore` para não ser versionado).*

| Coluna | Tipo | Unidade | Descrição |
|---|---|---|---|
| `dia` | Texto | `YYYY-MM-DD` | Data civil do dia agrupado. |
| `total_medicoes` | Inteiro | Unidades | Quantidade de medições horárias válidas presentes no dia. |
| `dia_completo` | Booleano | `True`/`False` | Indica se o dia possui a quantidade exata de medições esperadas para 24h (para $\Delta t = 1{,}0\text{ h}$, exige 24 medições). |
| `potencia_media_kw` | Numérico (`float`) | kW | Potência média aritmética registrada no dia. |
| `demanda_maxima_kw` | Numérico (`float`) | kW | Maior potência horária registrada no dia. |
| `consumo_kwh` | Numérico (`float`) | kWh | Energia elétrica acumulada no dia ($\sum P_i \times \Delta t$). |
| `participacao_percentual`| Numérico (`float`) | % | Fração percentual do consumo diário frente à energia total registrada no histórico consolidado. |
| `tarifa_aplicada_r_kwh`| Numérico (`float`) | R$/kWh | Tarifa fixa de referência utilizada para simulação financeira. |
| `custo_estimado_dia_r` | Numérico (`float`) | R$ | Estimativa linear de custo do dia ($E_{\text{dia}} \times \text{tarifa}$). |

---

## 2. Grandezas Físicas e Unidades

- **Potência Ativa ($P$)**: Medida em **quilowatts (kW)**. Representa a taxa média com que a energia elétrica é demandada ou convertida em trabalho útil durante o intervalo.
- **Tempo ($\Delta t$)**: Medido em **horas (h)**. No contrato da versão 1.0, o pipeline opera com $\Delta t = 1{,}0\text{ h}$.
- **Energia Elétrica ($E$)**: Medida em **quilowatts-hora (kWh)**. Quantidade física acumulada resultante da integração temporal da potência ativa ($1\text{ kWh} = 1\text{ kW} \times 1\text{ h}$).
- **Tarifa Elétrica**: Expressa em **Reais por quilowatt-hora (R$/kWh)**. Variável de referência configurada em [`config.py`](../config.py).
- **Fator de Carga ($FC$)**: Adimensional, expresso em **percentual (%)**. Razão entre a potência média e a demanda de pico.

---

## 3. Contrato Temporal e Regras de Validação

O módulo [`src/import_data.py`](../src/import_data.py) avalia cada linha do CSV através de critérios mutuamente exclusivos:

1. **Campos Obrigatórios e Nulos**:
   - Linhas com `data_hora` ou `potencia_kw` ausentes ou vazias são descartadas (`ausentes_descartados`).
2. **Formato de Data/Hora e Fuso Horário**:
   - Rejeita formatos não interpretáveis (`data_invalida`).
   - Rejeita explicitamente fusos horários (`UTC`, `GMT`, `+03:00`, `-03:00`, sufixo `Z`) e frações de segundo (`.123456`), preservando o carimbo como horário local ingênuo sem conversões silenciosas (`fora_contrato_horario`).
3. **Contrato de Início de Hora Cheia**:
   - Cada medição deve satisfazer `minute == 0`, `second == 0`, `microsecond == 0` e `nanosecond == 0`. Amostras sub-horárias (ex: `08:30`) são rejeitadas nesta versão (`fora_contrato_horario`).
4. **Finitude Numérica**:
   - Valores não numéricos ou não finitos (`float('inf')`, `float('-inf')`, `nan`) são rejeitados via `math.isfinite()` (`potencia_nao_numerica_ou_infinita`).
5. **Potência Negativa ($P < 0$)**:
   - Potências negativas não representam impossibilidade física na natureza (podem indicar injeção ou geração própria em redes bidirecionais), mas estão **fora do escopo de consumo unidirecional do PowerMonitor**, sendo descartadas para proteger os cálculos de consumo (`negativos_rejeitados`).
6. **Duplicatas e Conflitos**:
   - **Duplicatas Idênticas**: Mesma data/hora e exatamente o mesmo valor numérico de potência têm apenas a primeira ocorrência mantida (`duplicados_exatos_descartados`).
   - **Conflito de Medição**: Mesma data/hora com valores distintos de potência disparam erro explícito (`ValueError`), interrompendo o pipeline antes da gravação.
7. **Detecção de Lacunas Temporais**:
   - A função `identificar_lacunas_temporais` detecta horas faltantes entre os extremos cronológicos no CSV e no histórico acumulado do banco. As lacunas são reportadas sem interpolação artificial nem preenchimento por zero.

---

## 4. Formulação Matemática

### 4.1 Potência Média Horária ($\bar{P}$)
Calculada como a média aritmética das $N$ medições válidas no período:

$$\bar{P} = \frac{1}{N} \sum_{i=1}^{N} P_i \quad [\text{kW}]$$

### 4.2 Demanda Máxima de Pico ($P_{\text{máx}}$)
A maior potência horária registrada no período analisado:

$$P_{\text{máx}} = \max_{1 \le i \le N} (P_i) \quad [\text{kW}]$$

*Critério de Desempate:* Se mais de uma medição atingir o valor máximo, adota-se o critério determinístico de selecionar a primeira ocorrência cronológica (`data_hora ASC`).

### 4.3 Energia Consumida Acumulada ($E_{\text{total}}$)
A energia elétrica é a integral da potência ativa no tempo:

$$E_{\text{total}} = \sum_{i=1}^{N} \left( P_i \times \Delta t \right) \quad [\text{kWh}]$$

Mantendo as unidades explícitas: $\text{kW} \times \text{h} = \text{kWh}$. Para $\Delta t = 1{,}0\text{ h}$:

$$E_{\text{total}} = \sum_{i=1}^{N} \left( P_i \times 1{,}0\text{ h} \right) \quad [\text{kWh}]$$

### 4.4 Agregação Diária, Dias Parciais e Participação Percentual
Para cada data civil $d$:

$$E_{\text{dia}}(d) = \sum_{i \in d} \left( P_i \times \Delta t \right) \quad [\text{kWh}]$$

$$\bar{P}_{\text{dia}}(d) = \frac{1}{N_d} \sum_{i \in d} P_i \quad [\text{kW}]$$

$$\text{Participação}_{\text{dia}}(d) = \frac{E_{\text{dia}}(d)}{E_{\text{total}}} \times 100\%$$

Um dia é classificado como completo (`dia_completo = True`) quando o total de medições atinge a quantidade esperada:

$$N_{\text{esperado}} = \frac{24\text{ h}}{\Delta t}$$

Para $\Delta t = 1{,}0\text{ h}$, $N_{\text{esperado}} = 24$. Se $N_d < 24$, o dia é classificado como parcial (`dia_completo = False`), e o consumo reportado abrange estritamente os intervalos registrados.

*Nota sobre arredondamentos:* A participação diária é calculada a partir de valores não arredondados e formatada com duas casas decimais. Diferenças residuais na soma (ex: $99{,}99\%$ ou $100{,}01\%$) decorrem estritamente desse arredondamento. Se a energia total for zero, a participação é apresentada como não aplicável.

### 4.5 Fator de Carga ($FC$)
O Fator de Carga é a razão entre a potência média e a demanda máxima registrada:

$$FC = \frac{\bar{P}}{P_{\text{máx}}} \times 100\%$$

*Interpretação de Engenharia:* O fator de carga é um indicador do **grau de uniformidade da solicitação de potência** frente à capacidade de pico instalada. Valores elevados indicam carga distribuída de maneira uniforme, enquanto valores baixos indicam concentração de consumo em horários específicos. **O fator de carga não representa nem deve ser confundido com a eficiência energética dos equipamentos**. Se a demanda máxima for nula ($P_{\text{máx}} = 0$), o indicador é definido como não aplicável, evitando divisões por zero. Em períodos com lacunas, refere-se estritamente às horas disponíveis.

### 4.6 Dia de Maior Consumo Registrado
Identifica a data civil em que ocorreu o maior valor de $E_{\text{dia}}$. Em caso de empate, seleciona-se a data mais antiga (`dia ASC`). Quando o dia selecionado for parcial, o relatório explicita que a comparação frente a dias completos é limitada pela diferença de cobertura amostral.

### 4.7 Cobertura Temporal das Medições
Mede a integridade da série temporal no intervalo monitorado, delimitado entre o início da primeira medição ($T_{\min}$) e o encerramento da última hora amostrada ($T_{\max} + \Delta t$):

$$\text{Horas Esperadas} = \frac{T_{\max} - T_{\min}}{\Delta t} + 1$$

$$\text{Cobertura (\%)} = \frac{\text{Horas com Medições Válidas}}{\text{Horas Esperadas}} \times 100\%$$

*Premissa de bordas:* Uma cobertura de 100% entre os limites da amostragem não implica necessariamente que os dias civis inicial e final estejam completos (por exemplo, um monitoramento iniciado às 14:00 terá 10 horas registradas no primeiro dia, sendo classificado como parcial mesmo com cobertura íntegra naquele intervalo).

### 4.8 Estimativa Simplificada de Custo Financeiro
Multiplicação linear didática:

$$\text{Custo (R\$)} = E_{\text{total}} \, (\text{kWh}) \times \text{Tarifa} \, (\text{R\$/kWh})$$

*Distinção regulatória:* Esta estimativa não substitui nem equivale a uma fatura de concessionária de distribuição, pois não modela demandas contratadas, postos tarifários horossazonais (ponta e fora de ponta), bandeiras tarifárias nem encargos setoriais e tributos (ICMS, PIS, COFINS).

---

## 5. Visualização: Curva de Carga Semanal

O gráfico da curva de carga do arquivo de exemplo [`data/medicoes.csv`](../data/medicoes.csv) está salvo em [`docs/images/curva_de_carga.png`](images/curva_de_carga.png):

![Curva de Carga Horária Semanal](images/curva_de_carga.png)

### Como reproduzir o gráfico:
Para gerar novamente a imagem a partir do arquivo CSV atual, execute o script dedicado:

```bash
python scripts/gerar_curva_de_carga.py
```
O script lê `data/medicoes.csv` e regrava `docs/images/curva_de_carga.png` com título, eixos, unidades e identificação de dados simulados.
