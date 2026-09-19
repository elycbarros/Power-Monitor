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

### 1.4 Relatório Visual HTML Autocontido (`output/relatorio.html`)
*(Arquivo local estático gerado após a execução, listado no `.gitignore` para não ser versionado).*

O relatório visual é um arquivo HTML5 estático único, gerado offline sem dependências de rede (sem CDNs, fontes remotas ou bibliotecas externas), estruturado nas seguintes seções:
- **Cabeçalho:** Identificação do PowerMonitor, escopo temporal com significado dos limites, resolução amostral, carimbo de geração com fuso local e badge de origem dos dados.
- **Cards de Indicadores:** 6 cartões de destaque com métricas consolidadas e notas conceituais.
- **Gráficos Integrados em Base64:** Curva de carga (com corte em lacunas), barras diárias (com segregação de dias parciais) e mapa de calor dia &times; horário (com destaque de dados ausentes e potência zero).
- **Auditoria de Qualidade:** Balanço lote CSV vs histórico SQLite e alertas de consistência.
- **Síntese e Limitações Regulatórias:** Parágrafos interpretativos acompanhados da nota de delimitação legal.
- **Tabela Diária Responsiva:** Tabela acessível com rolagem horizontal isolada e padrão numérico brasileiro.

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

*Interpretação de Engenharia e Regulatória:* Definido na REN ANEEL nº 1.000/2021 (Art. 2º, XIX) como a razão entre a demanda média e a demanda máxima em um intervalo de tempo, o fator de carga expressa o **grau de uniformidade da solicitação de potência** frente ao pico de demanda observado. Valores elevados indicam carga distribuída de maneira uniforme no tempo, enquanto valores baixos indicam concentração de consumo em horários específicos. **O fator de carga não representa nem deve ser confundido com o fator de potência ($\cos \varphi$, Art. 302) nem com a eficiência energética dos equipamentos**. Se a demanda máxima for nula ($P_{\text{máx}} = 0$), o indicador é definido como não aplicável, evitando divisões por zero. Em períodos com lacunas, refere-se estritamente aos intervalos medidos.

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

*Distinção regulatória:* Esta estimativa constitui uma simulação linear para fins puramente educacionais e analíticos. Não substitui nem equivale a uma fatura de concessionária de distribuição, conforme detalhado na Seção 6.

---

## 5. Visualização de Dados e Relatório Gráfico

### 5.1 Relatório Visual Autocontido (`output/relatorio.html`)
O pipeline compila automaticamente um relatório visual estático completo e interativo via navegador em `output/relatorio.html`.
Principais premissas das visualizações:
- **Curva de Carga no Tempo:** A linha plota a potência ativa média no intervalo amostral. Em caso de lacunas temporais (dados ausentes), a grade temporal teórica é reindexada com `NaN`, **interrompendo a linha nos períodos sem medição** para não induzir presunção de registros inexistentes.
- **Consumo Diário:** Gráfico de barras ordenado cronologicamente, com diferenciação visual e textual entre dias completos (24h OK) e dias parciais (< 24h), além de destaque ao dia de maior consumo e anotações de participação percentual.
- **Mapa de Calor Operacional (Dia &times; Horário):** Matriz 2D onde cada célula representa um intervalo amostral. Intervalos ausentes são preenchidos com cinza neutro (`#e2e8f0`) com legenda dedicada, enquanto potências de zero quilowatt ($0\text{ kW}$) válidas são mapeadas em tom claro da escala (`#ffffcc`), evitando confusão entre ausência de dado e consumo nulo.
- **Sem Dependências de Rede:** Todas as figuras são geradas via Matplotlib (`backend Agg`) e embutidas diretamente no HTML como imagens Base64 (`data:image/png;base64,...`), viabilizando inspeção offline, compartilhamento por e-mail e preservação total de leiaute.

### 5.2 Curva de Carga Estática para Documentação (`docs/images/curva_de_carga.png`)
O gráfico da curva de carga do arquivo de exemplo de 7 dias [`data/medicoes.csv`](../data/medicoes.csv) está salvo como asset estático em [`docs/images/curva_de_carga.png`](images/curva_de_carga.png):

![Curva de Carga Horária Semanal](images/curva_de_carga.png)

#### Como reproduzir o gráfico avulso:
Para gerar novamente a imagem estática a partir do arquivo CSV de exemplo, execute o script dedicado:

```bash
python scripts/gerar_curva_de_carga.py
```
O script lê `data/medicoes.csv` e regrava `docs/images/curva_de_carga.png` com título, eixos, unidades e identificação de dados simulados.

---

## 6. Enquadramento Conceitual e Escopo Regulatório (REN ANEEL nº 1.000/2021)

### 6.1 Finalidade Educacional e Limites do Projeto
O **PowerMonitor** é uma aplicação voltada ao ensino de engenharia de dados aplicada ao setor elétrico. Tem por finalidade receber séries de telemetria, validar regras físicas e temporais, estruturar dados em SQL e calcular grandezas fundamentais de consumo e perfil de carga.

> [!IMPORTANT]
> O PowerMonitor **não é um sistema de tarifação ou faturamento comercial regulado**. O software não realiza cobranças legais, não emite faturas, não possui homologação perante a ANEEL ou o INMETRO e não valida conformidade regulatória de distribuidoras ou consumidores.

### 6.2 Conceitos Alinhados à REN ANEEL nº 1.000/2021
As definições adotadas na ferramenta guardam correspondência direta com os conceitos metrológicos e regulatórios estabelecidos na Resolução Normativa ANEEL nº 1.000/2021:

- **Demanda (Art. 2º, XI)**: Média da potência ativa solicitada à rede pela instalação elétrica ao longo de um intervalo de tempo especificado ($\Delta t$), expressa em quilowatts (kW).
- **Demanda Medida vs. Pico Observado (Art. 2º, XIII)**:
  - *Na regulação:* A "demanda medida" é a maior potência ativa integrada em intervalos contínuos de 15 minutos durante o ciclo mensal de faturamento.
  - *No PowerMonitor:* O software apura a maior potência média observada no passo amostral dos dados ($\Delta t = 1{,}0\text{ h}$, $30\text{ min}$ ou $15\text{ min}$). Embora o pipeline suporte dados com resolução de 15 minutos, essa capacidade analítica representa uma funcionalidade de amostragem temporal, e não uma conformidade homologada com os procedimentos de integração mensal de demanda faturável.
- **Energia Elétrica Ativa (Art. 2º, XVI)**: Integral da potência ativa demandada ao longo do tempo, convertível em trabalho útil, expressa em quilowatts-hora (kWh). Cada linha da série temporal representa a potência média durante o intervalo $\Delta t$, e a multiplicação direta $E_i = P_i \times \Delta t$ reflete a conversão física exata de energia no período.
- **Fator de Carga (Art. 2º, XIX)**: Razão entre a demanda média ($\bar{P}$) e a demanda máxima registrada ($P_{\text{máx}}$) no período monitorado. O indicador expressa a taxa de modulação e o aproveitamento do perfil de carga, dependendo estritamente da cobertura e resolução da medição.
- **Modalidades Tarifárias e Tarifa Branca (Art. 212)**:
  - No faturamento regulado, a *Tarifa Branca* aplica-se a unidades consumidoras do **Grupo B** (baixa tensão) e diferencia **exclusivamente os valores de tarifa de consumo de energia elétrica ativa (R$/kWh)** segundo os postos tarifários (ponta, intermediário e fora de ponta). No Grupo B, **não há cobrança de demanda faturável em R$/kW**.
  - O faturamento binômio com contratação e medição obrigatória de demanda em R$/kW é privativo do **Grupo A** (alta/média tensão, Art. 294), não devendo ser confundido com a estrutura da Tarifa Branca.

### 6.3 Componentes de Faturamento Excluídos do Escopo
Em conformidade com a natureza didática da ferramenta, os seguintes mecanismos regulados de faturamento da REN 1.000/2021 **não são implementados nem calculados**:

1. **Faturamento de Demanda e Ultrapassagem (Arts. 294, 295 e 301)**: Não há modelagem de demanda contratada, tolerâncias de 5% nem tarifas de ultrapassagem em R$/kW para o Grupo A.
2. **Custo de Disponibilidade (Arts. 290 e 291)**: Não há cobrança do consumo mínimo aplicável ao Grupo B por tipo de conexão (monofásica 30 kWh, bifásica 50 kWh ou trifásica 100 kWh).
3. **Energia Reativa e Fator de Potência (Arts. 302 a 304)**: O PowerMonitor analisa exclusivamente grandezas ativas (kW e kWh). Não há registros de energia reativa (kvarh), cálculo de fator de potência indutivo/capacitivo ($\cos \varphi$) nem apuração de encargos por reativos excedentes frente ao limite regulatório de 0,92.
4. **Postos Horários e Sazonalidade**: A tarifa do PowerMonitor é tratada como um parâmetro monômio linear constante, sem diferenciação horária (ponta, intermediária, fora de ponta) ou sazonal (seca/úmida).
5. **Bandeiras Tarifárias e Tributos**: Não são simulados os adicionais de bandeiras tarifárias (verde, amarela, vermelha P1/P2 ou escassez hídrica) nem os tributos incidentes na fatura (ICMS, PIS, COFINS e CIP/COSIP).
6. **Compensação de Geração Distribuída**: Não há contabilização de créditos de micro ou minigeração distribuída (Lei nº 14.300/2022).

### 6.4 Documento de Referência
- **Resolução Normativa ANEEL nº 1.000, de 7 de dezembro de 2021**, que estabelece as Regras de Prestação do Serviço Público de Distribuição de Energia Elétrica.
- **Fonte documental utilizada:** Reprodução disponibilizada pelo portal *Leis.org* (`www.leis.org`), com carimbo de impressão em 19/09/2026. A indicação dessa data expressa estritamente o registro de extração do documento de consulta, recomendando-se conferência das resoluções homologatórias e atos posteriores no Diário Oficial da União e no acervo oficial da ANEEL para quaisquer aplicações regulatórias formais.
