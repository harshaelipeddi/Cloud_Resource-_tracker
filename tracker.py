"""
Cloud Resource Tracker
======================
Collects AWS resource metrics (EC2, S3, RDS, IAM, VPC) and stores them in
SQLite. Designed to be run on a schedule (cron / Jenkins) and visualised in
Grafana via the SQLite datasource plugin.

Author :  Elipeddi Harshavardhan
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# ─────────────────────────────  Logging  ──────────────────────────────────────

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("tracker.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("cloud_tracker")

# ─────────────────────────────  Config  ───────────────────────────────────────

DB_PATH    = os.getenv("TRACKER_DB", "cloud_resources.db")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


# ═════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ═════════════════════════════════════════════════════════════════════════════

SCHEMA_SQL = """
-- EC2 snapshots
CREATE TABLE IF NOT EXISTS ec2_instances (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id    TEXT    NOT NULL,
    name           TEXT,
    instance_type  TEXT,
    state          TEXT,
    public_ip      TEXT,
    private_ip     TEXT,
    az             TEXT,
    region         TEXT,
    launch_time    TEXT,
    recorded_at    TEXT    NOT NULL
);

-- S3 snapshots
CREATE TABLE IF NOT EXISTS s3_buckets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket_name    TEXT    NOT NULL,
    region         TEXT,
    creation_date  TEXT,
    object_count   INTEGER,
    size_bytes     INTEGER,
    recorded_at    TEXT    NOT NULL
);

-- RDS snapshots
CREATE TABLE IF NOT EXISTS rds_instances (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    db_identifier   TEXT    NOT NULL,
    engine          TEXT,
    engine_version  TEXT,
    status          TEXT,
    instance_class  TEXT,
    storage_gb      INTEGER,
    multi_az        INTEGER,
    region          TEXT,
    recorded_at     TEXT    NOT NULL
);

-- IAM summary
CREATE TABLE IF NOT EXISTS iam_summary (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    users           INTEGER,
    groups          INTEGER,
    roles           INTEGER,
    policies        INTEGER,
    recorded_at     TEXT    NOT NULL
);

-- VPC snapshots
CREATE TABLE IF NOT EXISTS vpcs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    vpc_id         TEXT    NOT NULL,
    cidr_block     TEXT,
    state          TEXT,
    is_default     INTEGER,
    subnet_count   INTEGER,
    region         TEXT,
    recorded_at    TEXT    NOT NULL
);

-- Run log (one row per collection run)
CREATE TABLE IF NOT EXISTS collection_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT,
    error_msg    TEXT
);
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ec2_recorded  ON ec2_instances(recorded_at);",
    "CREATE INDEX IF NOT EXISTS idx_s3_recorded   ON s3_buckets(recorded_at);",
    "CREATE INDEX IF NOT EXISTS idx_rds_recorded  ON rds_instances(recorded_at);",
    "CREATE INDEX IF NOT EXISTS idx_vpc_recorded  ON vpcs(recorded_at);",
]


def get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    logger.info("Initialising database at %s", db_path)
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        for idx in _INDEXES:
            conn.execute(idx)
    logger.info("Database ready.")


# ═════════════════════════════════════════════════════════════════════════════
#  AWS COLLECTORS
# ═════════════════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tag(tags: list[dict], key: str) -> str | None:
    for t in tags or []:
        if t.get("Key") == key:
            return t.get("Value")
    return None


# ── EC2 ──────────────────────────────────────────────────────────────────────

def collect_ec2(region: str = AWS_REGION) -> list[dict]:
    logger.info("Collecting EC2  [%s]", region)
    client = boto3.client("ec2", region_name=region)
    rows: list[dict] = []
    try:
        paginator = client.get_paginator("describe_instances")
        for page in paginator.paginate():
            for res in page["Reservations"]:
                for inst in res["Instances"]:
                    rows.append({
                        "instance_id":   inst["InstanceId"],
                        "name":          _tag(inst.get("Tags"), "Name"),
                        "instance_type": inst.get("InstanceType"),
                        "state":         inst["State"]["Name"],
                        "public_ip":     inst.get("PublicIpAddress"),
                        "private_ip":    inst.get("PrivateIpAddress"),
                        "az":            inst.get("Placement", {}).get("AvailabilityZone"),
                        "region":        region,
                        "launch_time":   inst.get("LaunchTime", "").isoformat()
                                         if hasattr(inst.get("LaunchTime", ""), "isoformat") else None,
                        "recorded_at":   _now(),
                    })
        logger.info("  EC2 → %d instances", len(rows))
    except (BotoCoreError, ClientError) as exc:
        logger.error("EC2 collection error: %s", exc)
    return rows


# ── S3 ───────────────────────────────────────────────────────────────────────

def _bucket_region(s3_client: Any, bucket: str) -> str:
    try:
        resp = s3_client.get_bucket_location(Bucket=bucket)
        loc  = resp.get("LocationConstraint")
        return loc or "us-east-1"
    except ClientError:
        return "unknown"


def _bucket_stats(s3_client: Any, bucket: str) -> tuple[int, int]:
    """Return (object_count, total_size_bytes) using CloudWatch or 0,0 on error."""
    try:
        cw = boto3.client("cloudwatch", region_name="us-east-1")
        now = datetime.now(timezone.utc)
        def _metric(name: str) -> int:
            resp = cw.get_metric_statistics(
                Namespace="AWS/S3",
                MetricName=name,
                Dimensions=[
                    {"Name": "BucketName",  "Value": bucket},
                    {"Name": "StorageType", "Value": "AllStorageTypes"
                     if name == "BucketSizeBytes" else "AllObjects"},
                ],
                StartTime=now.replace(hour=0, minute=0, second=0),
                EndTime=now,
                Period=86400,
                Statistics=["Average"],
            )
            pts = resp.get("Datapoints", [])
            return int(pts[-1]["Average"]) if pts else 0
        return _metric("NumberOfObjects"), _metric("BucketSizeBytes")
    except (BotoCoreError, ClientError):
        return 0, 0


def collect_s3() -> list[dict]:
    logger.info("Collecting S3 buckets")
    s3 = boto3.client("s3")
    rows: list[dict] = []
    try:
        for bucket in s3.list_buckets().get("Buckets", []):
            name  = bucket["Name"]
            obj_count, size = _bucket_stats(s3, name)
            rows.append({
                "bucket_name":   name,
                "region":        _bucket_region(s3, name),
                "creation_date": bucket["CreationDate"].isoformat(),
                "object_count":  obj_count,
                "size_bytes":    size,
                "recorded_at":   _now(),
            })
        logger.info("  S3 → %d buckets", len(rows))
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 collection error: %s", exc)
    return rows


# ── RDS ──────────────────────────────────────────────────────────────────────

def collect_rds(region: str = AWS_REGION) -> list[dict]:
    logger.info("Collecting RDS  [%s]", region)
    client = boto3.client("rds", region_name=region)
    rows: list[dict] = []
    try:
        paginator = client.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db in page["DBInstances"]:
                rows.append({
                    "db_identifier":  db["DBInstanceIdentifier"],
                    "engine":         db["Engine"],
                    "engine_version": db.get("EngineVersion"),
                    "status":         db["DBInstanceStatus"],
                    "instance_class": db["DBInstanceClass"],
                    "storage_gb":     db.get("AllocatedStorage"),
                    "multi_az":       int(db.get("MultiAZ", False)),
                    "region":         region,
                    "recorded_at":    _now(),
                })
        logger.info("  RDS → %d instances", len(rows))
    except (BotoCoreError, ClientError) as exc:
        logger.error("RDS collection error: %s", exc)
    return rows


# ── IAM ──────────────────────────────────────────────────────────────────────

def collect_iam() -> dict:
    logger.info("Collecting IAM summary")
    iam = boto3.client("iam")
    try:
        acct = iam.get_account_summary()["SummaryMap"]
        row  = {
            "users":      acct.get("Users", 0),
            "groups":     acct.get("Groups", 0),
            "roles":      acct.get("Roles", 0),
            "policies":   acct.get("Policies", 0),
            "recorded_at": _now(),
        }
        logger.info("  IAM → users=%d groups=%d roles=%d policies=%d",
                    row["users"], row["groups"], row["roles"], row["policies"])
        return row
    except (BotoCoreError, ClientError) as exc:
        logger.error("IAM collection error: %s", exc)
        return {}


# ── VPC ──────────────────────────────────────────────────────────────────────

def collect_vpcs(region: str = AWS_REGION) -> list[dict]:
    logger.info("Collecting VPCs [%s]", region)
    ec2 = boto3.client("ec2", region_name=region)
    rows: list[dict] = []
    try:
        vpcs    = ec2.describe_vpcs()["Vpcs"]
        subnets = ec2.describe_subnets()["Subnets"]
        subnet_counts: dict[str, int] = {}
        for s in subnets:
            subnet_counts[s["VpcId"]] = subnet_counts.get(s["VpcId"], 0) + 1
        for vpc in vpcs:
            rows.append({
                "vpc_id":       vpc["VpcId"],
                "cidr_block":   vpc.get("CidrBlock"),
                "state":        vpc.get("State"),
                "is_default":   int(vpc.get("IsDefault", False)),
                "subnet_count": subnet_counts.get(vpc["VpcId"], 0),
                "region":       region,
                "recorded_at":  _now(),
            })
        logger.info("  VPCs → %d", len(rows))
    except (BotoCoreError, ClientError) as exc:
        logger.error("VPC collection error: %s", exc)
    return rows


# ═════════════════════════════════════════════════════════════════════════════
#  STORAGE
# ═════════════════════════════════════════════════════════════════════════════

def _bulk_insert(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    cols   = list(rows[0].keys())
    ph     = ", ".join(["?"] * len(cols))
    sql    = f'INSERT INTO {table} ({", ".join(cols)}) VALUES ({ph})'
    values = [[r.get(c) for c in cols] for r in rows]
    conn.executemany(sql, values)
    logger.debug("  stored %d rows → %s", len(rows), table)


def store_all(
    ec2_rows:  list[dict],
    s3_rows:   list[dict],
    rds_rows:  list[dict],
    iam_row:   dict,
    vpc_rows:  list[dict],
    db_path:   str = DB_PATH,
) -> None:
    with get_conn(db_path) as conn:
        _bulk_insert(conn, "ec2_instances", ec2_rows)
        _bulk_insert(conn, "s3_buckets",    s3_rows)
        _bulk_insert(conn, "rds_instances", rds_rows)
        if iam_row:
            _bulk_insert(conn, "iam_summary", [iam_row])
        _bulk_insert(conn, "vpcs", vpc_rows)
    logger.info("All data committed to database.")


# ═════════════════════════════════════════════════════════════════════════════
#  REPORT
# ═════════════════════════════════════════════════════════════════════════════

def print_summary(ec2, s3, rds, iam, vpcs) -> None:
    print("\n" + "═" * 55)
    print("  Cloud Resource Tracker — Collection Summary")
    print("═" * 55)
    print(f"  EC2 Instances  : {len(ec2):>6}")
    print(f"  S3 Buckets     : {len(s3):>6}")
    print(f"  RDS Instances  : {len(rds):>6}")
    print(f"  VPCs           : {len(vpcs):>6}")
    if iam:
        print(f"  IAM Users      : {iam.get('users',0):>6}")
        print(f"  IAM Roles      : {iam.get('roles',0):>6}")
    print("═" * 55)
    print(f"  Stored to      : {DB_PATH}")
    print("═" * 55 + "\n")


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════════

def run(region: str = AWS_REGION, db_path: str = DB_PATH) -> None:
    started = _now()
    init_db(db_path)

    conn = get_conn(db_path)
    run_id = conn.execute(
        "INSERT INTO collection_runs (started_at, status) VALUES (?, ?)",
        (started, "running")
    ).lastrowid
    conn.commit()
    conn.close()

    try:
        ec2  = collect_ec2(region)
        s3   = collect_s3()
        rds  = collect_rds(region)
        iam  = collect_iam()
        vpcs = collect_vpcs(region)
        store_all(ec2, s3, rds, iam, vpcs, db_path)
        status, err = "success", None
        print_summary(ec2, s3, rds, iam, vpcs)
    except Exception as exc:
        logger.exception("Unexpected error during collection")
        status, err = "error", str(exc)

    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE collection_runs SET finished_at=?, status=?, error_msg=? WHERE id=?",
            (_now(), status, err, run_id)
        )

    if status == "error":
        sys.exit(1)


if __name__ == "__main__":
    run()
