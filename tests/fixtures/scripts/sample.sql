-- sample.sql — Demo SQL file for MCP Factory sql_analyzer tests.
--
-- Exercises: stored procedures (T-SQL param style + paren style),
-- scalar functions, views, tables, and triggers so every extraction
-- path in sql_analyzer.py is hit at least once.

-- ────────────────────────────────────────────────────────────────────
-- Tables
-- ────────────────────────────────────────────────────────────────────

CREATE TABLE invocable (
    id           INTEGER      PRIMARY KEY AUTOINCREMENT,
    name         VARCHAR(255) NOT NULL,
    signature    TEXT,
    confidence   VARCHAR(20)  NOT NULL DEFAULT 'low',
    doc_comment  TEXT,
    parameters   TEXT,
    return_type  VARCHAR(100),
    source_file  VARCHAR(512),
    created_at   DATETIME     DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE analysis_run (
    id          INTEGER      PRIMARY KEY AUTOINCREMENT,
    target_path VARCHAR(512) NOT NULL,
    analyzer    VARCHAR(50),
    run_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    total_count INTEGER      DEFAULT 0
);

-- ────────────────────────────────────────────────────────────────────
-- Stored procedures  (T-SQL bare @param style)
-- ────────────────────────────────────────────────────────────────────

CREATE PROCEDURE usp_InsertInvocable
    @name        VARCHAR(255),
    @signature   TEXT        = NULL,
    @confidence  VARCHAR(20) = 'low',
    @doc_comment TEXT        = NULL,
    @parameters  TEXT        = NULL,
    @return_type VARCHAR(100) = NULL,
    @source_file VARCHAR(512) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO invocable
           (name, signature, confidence, doc_comment, parameters, return_type, source_file)
    VALUES (@name, @signature, @confidence, @doc_comment, @parameters, @return_type, @source_file);
    SELECT SCOPE_IDENTITY() AS new_id;
END;
GO

CREATE PROCEDURE usp_GetInvocablesByConfidence
    @confidence VARCHAR(20),
    @limit      INT = 100
AS
BEGIN
    SELECT TOP (@limit) *
    FROM   invocable
    WHERE  confidence = @confidence
    ORDER  BY name;
END;
GO

-- ────────────────────────────────────────────────────────────────────
-- Stored procedure  (parenthesised / PL/pgSQL style)
-- ────────────────────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE sp_LogAnalysisRun(
    IN p_target_path VARCHAR(512),
    IN p_analyzer    VARCHAR(50),
    IN p_total_count INTEGER
)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO analysis_run (target_path, analyzer, total_count)
    VALUES (p_target_path, p_analyzer, p_total_count);
END;
$$;

-- ────────────────────────────────────────────────────────────────────
-- Scalar functions
-- ────────────────────────────────────────────────────────────────────

CREATE FUNCTION fn_ConfidenceScore(
    @has_doc    BIT,
    @is_signed  BIT
)
RETURNS INT
AS
BEGIN
    DECLARE @score INT = 0;
    IF @has_doc  = 1 SET @score = @score + 50;
    IF @is_signed = 1 SET @score = @score + 30;
    RETURN @score;
END;
GO

CREATE OR REPLACE FUNCTION fn_ConfidenceLabel(
    p_score DECIMAL(5,2)
)
RETURNS VARCHAR(20)
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN p_score >= 80 THEN 'guaranteed'
        WHEN p_score >= 60 THEN 'high'
        WHEN p_score >= 40 THEN 'medium'
        ELSE                    'low'
    END;
$$;

-- ────────────────────────────────────────────────────────────────────
-- Views
-- ────────────────────────────────────────────────────────────────────

CREATE VIEW vw_HighConfidenceInvocables AS
SELECT id, name, signature, confidence, doc_comment, return_type
FROM   invocable
WHERE  confidence IN ('guaranteed', 'high');

CREATE OR REPLACE VIEW vw_AnalysisSummary AS
SELECT
    ar.id          AS run_id,
    ar.target_path,
    ar.analyzer,
    ar.total_count,
    COUNT(i.id)    AS stored_count,
    ar.run_at
FROM analysis_run ar
LEFT JOIN invocable i ON i.source_file = ar.target_path
GROUP BY ar.id;

-- ────────────────────────────────────────────────────────────────────
-- Trigger
-- ────────────────────────────────────────────────────────────────────

CREATE TRIGGER trg_UpdateRunCount
AFTER INSERT ON invocable
FOR EACH ROW
BEGIN
    UPDATE analysis_run
    SET    total_count = total_count + 1
    WHERE  target_path = NEW.source_file;
END;
