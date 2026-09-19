-- ====================================================================
-- PowerMonitor: Consultas SQL Analíticas
-- Banco de dados: SQLite (medicoes)
-- ====================================================================

-- 1. Potência Média Geral (kW)
-- Retorna a média aritmética de todas as medições de potência registradas.
-- Nome da consulta: POTENCIA_MEDIA
SELECT 
    AVG(potencia_kw) AS potencia_media_kw
FROM medicoes;

-- 2. Demanda Máxima e Horário de Ocorrência (kW)
-- Identifica o maior valor de potência ativa demandada e o respectivo instante.
-- Nome da consulta: DEMANDA_MAXIMA
SELECT
    data_hora,
    potencia_kw AS demanda_maxima_kw
FROM medicoes
ORDER BY potencia_kw DESC
LIMIT 1;

-- 3. Análise e Consolidação Diária
-- Agrupa os dados por dia (YYYY-MM-DD) calculando:
--   - Contagem de medições no dia
--   - Potência média do dia (kW)
--   - Demanda máxima do dia (kW)
--   - Energia consumida estimada (kWh), assumindo intervalo delta_t = 1 hora
-- Nome da consulta: ANALISE_DIARIA
SELECT
    DATE(data_hora) AS dia,
    COUNT(*) AS total_medicoes,
    ROUND(AVG(potencia_kw), 2) AS potencia_media_kw,
    ROUND(MAX(potencia_kw), 2) AS demanda_maxima_kw,
    ROUND(SUM(potencia_kw * 1.0), 2) AS consumo_estimado_kwh
FROM medicoes
GROUP BY DATE(data_hora)
ORDER BY dia;

-- 4. Indicadores Gerais Consolidados
-- Nome da consulta: RESUMO_GERAL
SELECT
    COUNT(*) AS total_medicoes,
    MIN(data_hora) AS data_inicio,
    MAX(data_hora) AS data_fim,
    ROUND(AVG(potencia_kw), 2) AS potencia_media_kw,
    ROUND(MAX(potencia_kw), 2) AS demanda_maxima_kw,
    ROUND(SUM(potencia_kw * 1.0), 2) AS consumo_total_kwh
FROM medicoes;
