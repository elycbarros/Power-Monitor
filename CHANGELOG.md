# Changelog — PowerMonitor

Todas as alterações notáveis deste projeto são documentadas neste arquivo.
O formato é baseado no padrão [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/) e adota o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

---

## [1.1.0] — 2026-09-19

### Adicionado
- **Suporte a Resoluções Sub-horárias (15 e 30 minutos):**
  - Flag `--intervalo` no CLI (`0.25` para 15 min, `0.5` para 30 min e `1.0` para 1h).
  - Validação de alinhamento à grade amostral (`:00`, `:15`, `:30`, `:45` para 15 min) rejeitando minutos fora da grade.
  - Auditoria de lacunas temporais com suporte à frequência de 15 minutos no CSV e no banco.
  - Suíte expandida para **30 testes automatizados** com teste E2E dedicado de 15 minutos (96 medições diárias com integral exata de 240,0 kWh).

---

## [1.0.0] — 2026-09-19

### Adicionado
- **Interface de Linha de Comando (CLI):** Suporte a argumentos via `argparse` em `main.py` (`--csv`, `--tarifa`, `--banco`, `--saida`, `--help`) mantendo retrocompatibilidade com `config.py`.
- **Indicadores Elétricos Avançados:**
  - Fator de Carga ($FC = P_{\text{média}} / P_{\text{pico}}$) com interpretação de modulação de carga.
  - Dia de Maior Consumo com desempate cronológico determinístico pela data mais antiga.
  - Participação percentual de cada dia frente ao consumo energético total no terminal e no CSV.
  - Auditoria de cobertura temporal de medições (horas medidas, esperadas, ausentes e percentual).
- **Tipagem Estrita com TypedDict:** Definição formal dos contratos de dados em `src/analysis.py` (`IndicadoresCompletosDict` e `CoberturaDict`).
- **Síntese Executiva Interpretativa:** Geração de texto baseado em regras técnicas, distinguindo observações numéricas de hipóteses operacionais e orientando investigações sem julgamento prévio.
- **Validação Temporal com Contrato Estrito:** Ingestão rígida com verificação de hora cheia (`HH:00`), rejeição de fusos explícitos (`UTC`, `GMT`, offsets, `Z`) e descarte de frações de segundo para evitar perda silenciosa de precisão.
- **Transações Atômicas com Rollback:** Persistência relacional em SQLite com comparação estrita de valores existentes; divergências de telemetria disparam `ROLLBACK` total do lote.
- **Consultas SQL Analíticas:** Arquivo `sql/queries.sql` contendo consultas para potência média, demanda máxima, resumo geral e dia de maior consumo.
- **Curva de Carga Horária:** Script de geração de gráfico semanal (`scripts/gerar_curva_de_carga.py`) com padrão visual de engenharia.
- **Integração Contínua (CI):** Workflow do GitHub Actions testando matriz de Python 3.10 a 3.13 com `pytest-cov`.
- **Documentação Técnica Aprofundada:** Diretório `docs/` com especificações de arquitetura, metodologia de dados e relatório de validação e reprodutibilidade.

### Corrigido
- Rejeição e validação estrita de valores infinitos (`inf`, `-inf`) e potências negativas na ingestão do CSV.
- Contabilidade estrita de descarte de linhas calculada como a soma exata das categorias mutuamente exclusivas (`total_lidos == registros_validos + linhas_descartadas`).
- Idempotência estrita na persistência do SQLite para reexecuções sucessivas sem duplicar registros.
- Eliminação de recálculo redundante de `calcular_consumo_diario` no pipeline principal.
- Segregação de dependências: `pytest` e `pytest-cov` movidos exclusivamente para `requirements-dev.txt`.

### Testes
- Suíte automatizada com **29 testes** cobrindo unidades matemáticas, casos de borda, persistência com rollback, concordância SQL vs. Pandas e execução ponta a ponta.
- Cobertura de código atingindo **88%** consolidada via `pytest-cov`.
