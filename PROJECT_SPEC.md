# PowerMonitor: Especificação do Projeto (PROJECT_SPEC)

> **Status do Documento:** Especificação funcional de referência da Versão 1.0 (Planejamento Inicial e Escopo Implementado).  
> **Última Atualização:** Setembro/2026.  
> **Relação com a Implementação:** Este documento registra os requisitos previstos originalmente. Os refinamentos técnicos decorrentes da implementação prática (como validação de finitude com `math.isfinite`, contrato horário rígido `HH:00`, transações com `ROLLBACK` total em conflito de valores e testes automatizados de concordância SQL/Pandas) encontram-se detalhados na documentação técnica complementar em [`docs/`](docs/).

---

## 1. Visão Geral

O **PowerMonitor** é um projeto educacional e de portfólio voltado à Engenharia Elétrica e Análise de Dados.

O sistema processa medições de potência elétrica ao longo do tempo, armazena os dados em um banco relacional e gera indicadores relacionados ao consumo e à demanda de energia.

O projeto tem como objetivo aplicar, de forma integrada:
- Python
- Pandas
- SQL
- SQLite
- Análise de dados
- Git/GitHub
- Conceitos fundamentais de Engenharia Elétrica

A primeira versão utiliza dados simulados armazenados em CSV.

---

## 2. Objetivo

Construir um pipeline estruturado:

$$\text{CSV} \longrightarrow \text{Validação} \longrightarrow \text{Pandas} \longrightarrow \text{SQLite} \longrightarrow \text{SQL} \longrightarrow \text{Indicadores} \longrightarrow \text{Relatório}$$

O sistema executa os seguintes passos:
1. Leitura de medições elétricas de um arquivo CSV;
2. Validação técnica dos dados recebidos (tipagem, finitude, contrato horário e física);
3. Tratamento dos dados utilizando Pandas;
4. Armazenamento das medições em SQLite com integridade transacional;
5. Execução de consultas SQL para recuperação histórica e concordância analítica;
6. Cálculo de indicadores de potência média, demanda de pico e consumo energético;
7. Exibição de relatório no terminal e exportação em CSV.

---

## 3. Escopo da Versão 1.0

### Entrada
- Arquivo: `data/medicoes.csv`
- Formato esperado:
  ```csv
  data_hora,potencia_kw
  2026-08-01 08:00,12.4
  2026-08-01 09:00,15.8
  2026-08-01 10:00,18.1
  2026-08-01 11:00,17.3
  ```
- Caráter dos dados: Dados simulados sintetizados para fins educacionais e demonstrativos.

### Processamento
- Validação de presença das colunas obrigatórias;
- Contrato temporal: cada timestamp deve representar o início de uma hora cheia (`minute == 0`, `second == 0`);
- Rejeição de valores não finitos (`NaN`, `Inf`, `-Inf`) e não numéricos;
- Rejeição de valores negativos de potência ativa ($P < 0$);
- Rejeição e reversão (`ROLLBACK`) em caso de registros com mesmo timestamp e potências divergentes;
- Idempotência estrita para reimportação de medições idênticas;
- Detecção e sinalização de lacunas temporais sem preenchimento artificial.

### Saída
- Total de medições no histórico acumulado e novas medições processadas;
- Potência média horária (kW);
- Maior potência média horária (pico em kW) e data/hora da ocorrência;
- Energia acumulada estimada (kWh);
- Tabela de consumo diário (com indicação de dias completos de 24h vs. parciais);
- Estimativa simplificada de custo financeiro (R$).

---

## 4. Premissas de Engenharia Elétrica

As medições operam em intervalos regulares de 1 hora ($\Delta t = 1{,}0\text{ h}$).

$$\text{Energia (kWh)} = \text{Potência Média (kW)} \times \text{Tempo (h)}$$

Para $\Delta t = 1\text{ h}$:
$$\text{Energia} \approx \text{Potência registrada} \times 1\text{ hora}$$

**Distinção Fundamental de Engenharia:**
- O campo `potencia_kw` expressa a potência ativa média demandada naquele intervalo. O software não confunde potência com energia acumulada.
- O pico de demanda reportado corresponde à maior potência média horária, distinguindo-se da demanda regulamentada de faturamento (apurada em intervalos integrados de 15 minutos segundo critérios tarifários de ponta e fora de ponta).

---

## 5. Estrutura do Banco de Dados

Banco: **SQLite**  
Arquivo: `database/power_monitor.db`

```sql
CREATE TABLE IF NOT EXISTS medicoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora DATETIME NOT NULL UNIQUE,
    potencia_kw REAL NOT NULL
);
```

---

## 6. Critérios de Aceite e Conclusão da v1.0

- [x] Leitura de CSV com validação por linha e contabilidade estrita;
- [x] Rejeição de potências negativas e não finitas (`NaN`, `Inf`);
- [x] Contrato temporal horário estrito (`HH:00`, sem fusos nem frações);
- [x] Armazenamento idempotente em SQLite com transação atômica;
- [x] Detecção de conflitos de medição com reversão total do lote (`ROLLBACK`);
- [x] Sinalização de lacunas temporais no lote e no histórico consolidado;
- [x] Cálculo de potência média, demanda de pico e integral de energia;
- [x] Cálculo do fator de carga da instalação e cobertura temporal;
- [x] Agrupamento diário com participação percentual e identificação de dias completos vs parciais;
- [x] Identificação determinística do dia de maior consumo e desempates cronológicos;
- [x] Síntese executiva interpretativa baseada em dados no relatório;
- [x] Testes de concordância matemática entre consultas de `sql/queries.sql` e métodos do Pandas;
- [x] Exportação de relatório em CSV e exibição no terminal;
- [x] Suíte de testes automatizados abrangente com pytest;
- [x] Configuração local de CI via GitHub Actions;
- [x] Documentação técnica completa.
