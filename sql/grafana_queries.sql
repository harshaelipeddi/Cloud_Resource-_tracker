-- ═══════════════════════════════════════════════════════════════
--  Cloud Resource Tracker — Grafana SQL Queries
--  Use these in Grafana → SQLite datasource panels
-- ═══════════════════════════════════════════════════════════════


-- ── PANEL 1: EC2 Instance Count Over Time (Time Series) ─────────────────────
SELECT
    recorded_at  AS time,
    COUNT(*)     AS instance_count
FROM ec2_instances
GROUP BY recorded_at
ORDER BY recorded_at;


-- ── PANEL 2: EC2 Instances by State (Pie / Bar) ──────────────────────────────
SELECT
    state,
    COUNT(*) AS count
FROM ec2_instances
WHERE recorded_at = (SELECT MAX(recorded_at) FROM ec2_instances)
GROUP BY state
ORDER BY count DESC;


-- ── PANEL 3: ec2 Instances by Type (latest snapshot) ────────────────────────
SELECT
    instance_type,
    COUNT(*) AS count
FROM ec2_instances
WHERE recorded_at = (SELECT MAX(recorded_at) FROM ec2_instances)
GROUP BY instance_type
ORDER BY count DESC;


-- ── PANEL 4: S3 Total Storage Over Time (Time Series) ────────────────────────
SELECT
    recorded_at                  AS time,
    SUM(size_bytes) / 1073741824.0 AS total_size_gb
FROM s3_buckets
GROUP BY recorded_at
ORDER BY recorded_at;


-- ── PANEL 5: S3 Buckets by Region (latest snapshot, Bar) ─────────────────────
SELECT
    region,
    COUNT(*)           AS bucket_count,
    SUM(size_bytes) / 1073741824.0 AS size_gb
FROM s3_buckets
WHERE recorded_at = (SELECT MAX(recorded_at) FROM s3_buckets)
GROUP BY region
ORDER BY bucket_count DESC;


-- ── PANEL 6: RDS Instance Count Over Time (Time Series) ──────────────────────
SELECT
    recorded_at  AS time,
    COUNT(*)     AS rds_count
FROM rds_instances
GROUP BY recorded_at
ORDER BY recorded_at;


-- ── PANEL 7: RDS Instances by Engine (Pie, latest snapshot) ──────────────────
SELECT
    engine,
    COUNT(*) AS count
FROM rds_instances
WHERE recorded_at = (SELECT MAX(recorded_at) FROM rds_instances)
GROUP BY engine
ORDER BY count DESC;


-- ── PANEL 8: RDS Total Allocated Storage (latest snapshot) ───────────────────
SELECT
    db_identifier,
    engine,
    instance_class,
    storage_gb,
    status,
    CASE multi_az WHEN 1 THEN 'Yes' ELSE 'No' END AS multi_az
FROM rds_instances
WHERE recorded_at = (SELECT MAX(recorded_at) FROM rds_instances)
ORDER BY storage_gb DESC;


-- ── PANEL 9: IAM Summary Over Time (Time Series, multi-metric) ───────────────
SELECT
    recorded_at AS time,
    users,
    groups,
    roles,
    policies
FROM iam_summary
ORDER BY recorded_at;


-- ── PANEL 10: VPC Overview (Table, latest snapshot) ──────────────────────────
SELECT
    vpc_id,
    cidr_block,
    state,
    CASE is_default WHEN 1 THEN 'Yes' ELSE 'No' END AS is_default,
    subnet_count,
    region
FROM vpcs
WHERE recorded_at = (SELECT MAX(recorded_at) FROM vpcs)
ORDER BY is_default DESC, subnet_count DESC;


-- ── PANEL 11: Collection Run History (Table) ──────────────────────────────────
SELECT
    id,
    started_at,
    finished_at,
    ROUND(
        (JULIANDAY(finished_at) - JULIANDAY(started_at)) * 86400,
        2
    ) AS duration_sec,
    status,
    COALESCE(error_msg, '—') AS error
FROM collection_runs
ORDER BY started_at DESC
LIMIT 20;


-- ── PANEL 12: Resource Summary (Single-row stat panel) ───────────────────────
SELECT
    (SELECT COUNT(*) FROM ec2_instances
     WHERE recorded_at = (SELECT MAX(recorded_at) FROM ec2_instances)) AS ec2_instances,
    (SELECT COUNT(*) FROM s3_buckets
     WHERE recorded_at = (SELECT MAX(recorded_at) FROM s3_buckets))    AS s3_buckets,
    (SELECT COUNT(*) FROM rds_instances
     WHERE recorded_at = (SELECT MAX(recorded_at) FROM rds_instances)) AS rds_instances,
    (SELECT COUNT(*) FROM vpcs
     WHERE recorded_at = (SELECT MAX(recorded_at) FROM vpcs))          AS vpcs,
    (SELECT users FROM iam_summary
     ORDER BY recorded_at DESC LIMIT 1)                                AS iam_users;
