# PowerMonitor
## Análise de Consumo e Demanda de Energia Elétrica

## 1. Visão Geral

O PowerMonitor é um projeto educacional e de portfólio voltado à Engenharia Elétrica e Análise de Dados.

O sistema processa medições de potência elétrica ao longo do tempo, armazena os dados em um banco relacional e gera indicadores relacionados ao consumo e à demanda de energia.

O projeto tem como objetivo aplicar, de forma integrada:

- Python
- Pandas
- SQL
- SQLite
- Análise de dados
- Git/GitHub
- Conceitos básicos de Engenharia Elétrica

A primeira versão utiliza dados simulados armazenados em CSV. Futuramente, o projeto poderá consumir dados provenientes de APIs.

---

## 2. Objetivo

Construir um pipeline simples:

CSV → Validação → Pandas → SQLite → SQL → Indicadores → Relatório

O sistema deverá:

1. Ler medições elétricas de um arquivo CSV.
2. Validar os dados recebidos.
3. Tratar os dados utilizando Pandas.
4. Armazenar as medições em SQLite.
5. Executar consultas SQL.
6. Calcular indicadores de consumo e demanda.
7. Gerar um relatório com os resultados.

---

## 3. Escopo da Versão 1.0

A versão inicial deve ser simples e funcional.

### Entrada

Arquivo:
`data/medicoes.csv`

Formato:
```csv
data_hora,potencia_kw
2026-08-01 08:00,12.4
2026-08-01 09:00,15.8
2026-08-01 10:00,18.1
2026-08-01 11:00,17.3
```

Os dados utilizados inicialmente serão simulados e deverão ser identificados como tal na documentação.

### Processamento

O sistema deverá:
- carregar o CSV;
- converter data_hora para datetime;
- converter potencia_kw para valor numérico;
- identificar registros inválidos;
- verificar valores ausentes;
- rejeitar valores negativos de potência;
- armazenar registros válidos no banco.

### Saída

O sistema deverá apresentar:
- número de medições;
- potência média;
- demanda máxima;
- data/hora da demanda máxima;
- consumo estimado;
- consumo diário;
- estimativa de custo de energia.

---

## 4. Premissas de Engenharia

Para simplificar a primeira versão, as medições serão realizadas em intervalos regulares de uma hora.

Assim:

$$\text{Energia (kWh)} = \text{Potência média (kW)} \times \text{Tempo (h)}$$

Para intervalos de uma hora:
$$\text{Energia} \approx \text{Potência registrada} \times 1\text{ hora}$$

Exemplo:
- Potência = 15 kW
- Tempo = 1 h
- Energia = 15 kWh

**IMPORTANTE:**
Essa simplificação depende da interpretação da coluna `potencia_kw` como potência média durante o intervalo.
O software não deverá tratar simplesmente a soma de valores instantâneos de potência como consumo sem considerar o intervalo de medição.

---

## 5. Indicadores

### 5.1 Potência média
Média das medições de potência (kW).

### 5.2 Demanda máxima
Maior potência registrada no período analisado (kW).

### 5.3 Horário de maior demanda
Data e hora correspondentes à maior demanda registrada.

### 5.4 Energia consumida estimada
Para cada intervalo:
`energia_kwh = potencia_kw * intervalo_horas`
O consumo total será a soma desses valores.

### 5.5 Consumo diário
Agrupar as medições por data e calcular a energia estimada consumida em cada dia.

### 5.6 Custo estimado
Utilizar uma tarifa configurável:
`custo = consumo_kwh * tarifa_kwh`
A tarifa utilizada será apenas uma variável configurável do projeto.

---

## 6. Estrutura do Projeto

```
power-monitor/
├── data/
│   └── medicoes.csv
├── database/
│   └── power_monitor.db
├── output/
│   └── relatorio.csv
├── sql/
│   └── queries.sql
├── src/
│   ├── __init__.py
│   ├── database.py
│   ├── import_data.py
│   ├── analysis.py
│   └── report.py
├── tests/
│   └── test_analysis.py
├── .gitignore
├── config.py
├── main.py
├── requirements.txt
├── README.md
└── PROJECT_SPEC.md
```

---

## 7. Banco de Dados

Banco: SQLite
Arquivo: `database/power_monitor.db`

### Tabela `medicoes`
```sql
CREATE TABLE IF NOT EXISTS medicoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora DATETIME NOT NULL UNIQUE,
    potencia_kw REAL NOT NULL
);
```

---

## 8. Princípios do Projeto

1. Código simples.
2. Clareza.
3. Separação de responsabilidades.
4. Dados rastreáveis.
5. Validação das entradas.
6. Testes básicos.
7. Documentação.
8. Commits Git pequenos e compreensíveis.
