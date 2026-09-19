# PowerMonitor: Análise de Consumo e Demanda de Energia Elétrica

O **PowerMonitor** é um projeto educacional e de portfólio desenvolvido para integrar conceitos fundamentais de **Engenharia Elétrica**, **Python**, **Pandas** e **SQL/SQLite**.

O sistema processa medições de potência ativa ao longo do tempo, armazena os dados validados em um banco de dados relacional e calcula os principais indicadores técnicos de consumo e demanda energética.

---

## 1. Fluxo de Execução (Pipeline)

O projeto implementa um pipeline de dados estruturado e rastreável:

```
CSV (Entrada) ➔ Validação Técnica ➔ Tratamento (Pandas) ➔ SQLite ➔ Consultas SQL ➔ Indicadores ➔ Relatório Terminal & CSV
```

---

## 2. Premissas de Engenharia Elétrica

1. **Potência Média e Intervalo Regular**:
   - As medições são registradas em intervalos regulares de 1 hora ($\Delta t = 1{,}0\text{ h}$).
   - O campo `potencia_kw` representa a **potência ativa média demandada** durante aquele intervalo horário.

2. **Cálculo da Energia Consumida (Consumo)**:
   - A energia elétrica não é obtida por uma soma descontextualizada de valores pontuais, mas pela integração da potência no tempo:
     $$\text{Energia (kWh)} = \text{Potência Média (kW)} \times \Delta t\text{ (h)}$$
   - Para intervalos de 1 hora:
     $$\text{Energia (kWh)} \approx \text{Potência (kW)} \times 1{,}0$$
   - Consumo total acumulado:
     $$\text{Consumo Total} = \sum_{i=1}^{N} \text{Energia}_i$$

3. **Demanda Máxima**:
   - Maior valor de potência ativa solicitada no período analisado ($\max(P_i)$) e o instante exato de sua ocorrência.

4. **Estimativa de Custo**:
   - Multiplicação do consumo apurado por uma tarifa configurável (R$/kWh):
     $$\text{Custo (R\$)} = \text{Consumo (kWh)} \times \text{Tarifa (R\$/kWh)}$$

> [!NOTE]
> **Aviso de Dados Simulados**:
> Os dados contidos em `data/medicoes.csv` e as tarifas em `config.py` são gerados para fins puramente didáticos e educacionais, não refletindo faturamentos ou medições reguladas de concessionárias específicas.

---

## 3. Estrutura do Projeto

```
power-monitor/
│
├── data/
│   └── medicoes.csv          # Arquivo de medições simuladas (168h / 7 dias)
│
├── database/
│   └── power_monitor.db      # Banco de dados relacional SQLite
│
├── output/
│   └── relatorio.csv         # Relatório consolidado exportado
│
├── sql/
│   └── queries.sql           # Consultas analíticas SQL documentadas
│
├── src/
│   ├── __init__.py
│   ├── database.py           # Conexão, criação de tabelas e persistência SQLite
│   ├── import_data.py        # Leitura, parsing e validações técnicas (Pandas)
│   ├── analysis.py           # Cálculos de indicadores técnicos e financeiros
│   └── report.py             # Formatação no terminal e exportação CSV
│
├── tests/
│   └── test_analysis.py      # Testes automatizados com pytest
│
├── .gitignore                # Arquivos ignorados no versionamento Git
├── config.py                 # Configurações globais, caminhos e tarifa
├── main.py                   # Orquestrador do pipeline
├── requirements.txt          # Dependências do projeto (pandas, pytest)
├── README.md                 # Documentação principal
└── PROJECT_SPEC.md           # Especificação de requisitos da v1.0
```

---

## 4. Instalação e Configuração

### Pré-requisitos
- Python 3.10 ou superior
- Git

### Passo a passo

1. **Clone ou acesse o repositório:**
   ```bash
   cd /Users/elydocarmobarros/Projects/power-monitor
   ```

2. **Crie e ative o ambiente virtual:**
   ```bash
   # No macOS / Linux:
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   ```

---

## 5. Execução do Pipeline

Para executar o pipeline completo:

```bash
python main.py
```

### Exemplo de Saída no Terminal:

```
======================================================================
                    P O W E R M O N I T O R                   
        Análise de Consumo e Demanda de Energia Elétrica      
======================================================================

Período analisado:
01/08/2026 a 07/08/2026

Medições processadas:
168

Potência média:
14,52 kW

Demanda máxima:
27,80 kW

Horário da demanda máxima:
05/08/2026 18:00

Energia estimada:
2.439,36 kWh

Custo estimado:
R$ 1.829,52 (tarifa de simulação: R$ 0,75/kWh)

----------------------------------------------------------------------
RESUMO DE CONSUMO DIÁRIO:
----------------------------------------------------------------------
Data         | Medições | Pot. Média (kW)  | Demanda Máx (kW) | Consumo (kWh) 
----------------------------------------------------------------------
2026-08-01   | 24       | 13,85            | 25,60            | 332,50        
...
======================================================================
Observação:
Resultados calculados a partir de dados simulados para fins educacionais.
Os valores acima não representam faturamento real de concessionária.
======================================================================
```

---

## 6. Execução dos Testes

Para rodar a suíte de testes unitários com o `pytest`:

```bash
pytest
```

Ou com detalhes por teste:

```bash
pytest -v
```

Os testes cobrem:
- Potência média
- Demanda máxima e localização de data/hora
- Consumo energético em kWh considerando intervalos
- Estimativa de custos financeiros
- Rejeição e filtragem de potências negativas
- Tratamento de registros corrompidos e ausentes
- Idempotência na inserção no banco de dados SQLite

---

## 7. Próximos Passos (Versão 2.0)

Conforme o planejamento de evolução do projeto:
- Integração com dados reais via API REST;
- Gráficos interativos de curva de carga diária e sazonal;
- Visualização em dashboard interativo utilizando **Streamlit**;
- Detecção automatizada de anomalias e ultrapassagens de demanda contratada;
- Migração opcional para PostgreSQL com Docker.
