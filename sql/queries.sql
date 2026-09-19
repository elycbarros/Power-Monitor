-- ====================================================================
-- PowerMonitor: Consultas SQL Analíticas
-- Banco de dados: SQLite (tabela: medicoes)
-- ====================================================================

-- 1. Potência Média Geral (kW)
-- Nome: POTENCIA_MEDIA
SELECT 
    AVG(potencia_kw) AS potencia_media_kw
FROM medicoes;

-- 2. Demanda Máxima e Horário de Ocorrência (kW)
-- Desempate determinístico pela primeira ocorrência cronológica (data_hora ASC)
-- Nome: DEMANDA_MAXIMA
SELECT
    data_hora,
    potencia_kw AS demanda_maxima_kw
FROM medicoes
ORDER BY potencia_kw DESC, data_hora ASC
LIMIT 1;

-- 3. Análise e Consolidação Diária (com Participação Percentual)
-- Nome: ANALISE_DIARIA
SELECT
    DATE(data_hora) AS dia,
    COUNT(*) AS total_medicoes,
    ROUND(AVG(potencia_kw), 2) AS potencia_media_kw,
    ROUND(MAX(potencia_kw), 2) AS demanda_maxima_kw,
    ROUND(SUM(potencia_kw * 1.0), 2) AS consumo_estimado_kwh,
    ROUND(SUM(potencia_kw * 1.0) / (SELECT SUM(potencia_kw * 1.0) FROM medicoes) * 100.0, 2) AS participacao_percentual
FROM medicoes
GROUP BY DATE(data_hora)
ORDER BY dia ASC;

-- 4. Indicadores Gerais Consolidados (com Fator de Carga)
-- Nome: RESUMO_GERAL
SELECT
    COUNT(*) AS total_medicoes,
    MIN(data_hora) AS data_inicio,
    MAX(data_hora) AS data_fim,
    ROUND(AVG(potencia_kw), 2) AS potencia_media_kw,
    ROUND(MAX(potencia_kw), 2) AS demanda_maxima_kw,
    ROUND(SUM(potencia_kw * 1.0), 2) AS consumo_total_kwh,
    ROUND(AVG(potencia_kw) / MAX(potencia_kw) * 100.0, 2) AS fator_carga_percentual
FROM medicoes;

-- 5. Dia de Maior Consumo Registrado
-- Desempate determinístico pela data mais antiga (dia ASC)
-- Nome: DIA_MAIOR_CONSUMO
SELECT
    DATE(data_hora) AS dia,
    ROUND(SUM(potencia_kw * 1.0), 2) AS consumo_diario_kwh
FROM medicoes
GROUP BY DATE(data_hora)
ORDER BY consumo_diario_kwh DESC, dia ASC
LIMIT 1;

