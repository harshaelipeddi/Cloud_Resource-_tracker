"""
Generate Sample Data for Cloud Resource Tracker
================================================
Generates 5 days of realistic, historical AWS resource snapshot data
and inserts it into the SQLite database. This allows testing the Grafana
dashboard with rich, time-series visualizations immediately.

Usage:
    python scripts/generate_sample_data.py
"""

from __future__ import annotations

import os
import sys
import sqlite3
import random
from datetime import datetime, timedelta, timezone

# Add parent directory to path to import tracker
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tracker


def generate_data() -> None:
    db_path = tracker.DB_PATH
    print(f"Initializing database at: {os.path.abspath(db_path)}")
    tracker.init_db(db_path)

    # We will generate data for the last 5 days, running every 6 hours (20 intervals)
    now = datetime.now(timezone.utc)
    intervals = 20
    time_step = timedelta(hours=6)
    start_time = now - (intervals * time_step)

    print(f"Generating {intervals} snapshots of sample data starting from {start_time.isoformat()}...")

    # Static metadata that doesn't change much
    region = "us-east-1"
    vpc_id_1 = "vpc-0a1b2c3d4e5f6g7h8"
    vpc_id_2 = "vpc-0defaultvpc1234"

    ec2_base = [
        {"instance_id": "i-01111111111111111", "name": "prod-web-server-1", "instance_type": "t3.medium", "state": "running", "az": "us-east-1a"},
        {"instance_id": "i-02222222222222222", "name": "prod-web-server-2", "instance_type": "t3.medium", "state": "running", "az": "us-east-1b"},
        {"instance_id": "i-03333333333333333", "name": "prod-db-replica", "instance_type": "r5.large", "state": "running", "az": "us-east-1a"},
        {"instance_id": "i-04444444444444444", "name": "dev-application", "instance_type": "t3.small", "state": "running", "az": "us-east-1b"},
        {"instance_id": "i-05555555555555555", "name": "dev-testing-runner", "instance_type": "t3.micro", "state": "stopped", "az": "us-east-1c"},
        {"instance_id": "i-06666666666666666", "name": "temp-sandbox", "instance_type": "t2.nano", "state": "stopped", "az": "us-east-1a"},
    ]

    s3_base = [
        {"bucket_name": "company-production-assets", "region": "us-east-1", "creation_date": (now - timedelta(days=100)).isoformat(), "base_objects": 1500, "base_bytes": 45 * 1024 * 1024 * 1024},
        {"bucket_name": "company-db-backups-daily", "region": "us-east-1", "creation_date": (now - timedelta(days=50)).isoformat(), "base_objects": 50, "base_bytes": 120 * 1024 * 1024 * 1024},
        {"bucket_name": "dev-user-uploads-temp", "region": "us-west-2", "creation_date": (now - timedelta(days=20)).isoformat(), "base_objects": 300, "base_bytes": 2 * 1024 * 1024 * 1024},
    ]

    rds_base = [
        {"db_identifier": "prod-aurora-cluster", "engine": "aurora-mysql", "engine_version": "8.0.mysql_aurora.3.04.0", "status": "available", "instance_class": "db.r5.xlarge", "storage_gb": 250, "multi_az": 1},
        {"db_identifier": "dev-postgres-db", "engine": "postgres", "engine_version": "15.4", "status": "available", "instance_class": "db.t3.medium", "storage_gb": 20, "multi_az": 0},
    ]

    # Insert data chronologically
    for i in range(intervals + 1):
        timestamp = (start_time + (i * time_step)).isoformat()
        
        # 1. Simulate EC2 changes (e.g. dev-testing-runner and temp-sandbox starting/stopping)
        ec2_rows = []
        for inst in ec2_base:
            state = inst["state"]
            # Randomly toggle dev/temp instances state
            if inst["name"] == "dev-testing-runner":
                state = "running" if (i % 4 == 0 or i % 4 == 1) else "stopped"
            elif inst["name"] == "temp-sandbox":
                # Sandbox only exists in the middle of the timeline
                if 5 <= i <= 15:
                    state = "running" if (i % 2 == 0) else "stopped"
                else:
                    continue  # Doesn't exist yet / deleted
            
            ec2_rows.append({
                "instance_id": inst["instance_id"],
                "name": inst["name"],
                "instance_type": inst["instance_type"],
                "state": state,
                "public_ip": "54.210.12.34" if state == "running" else None,
                "private_ip": "10.0.1.15" if state == "running" else None,
                "az": inst["az"],
                "region": region,
                "launch_time": (start_time + (i * time_step) - timedelta(hours=12)).isoformat(),
                "recorded_at": timestamp,
            })

        # 2. Simulate S3 growth
        s3_rows = []
        for bucket in s3_base:
            # Linear growth with some randomness
            growth_factor = 1.0 + (i * 0.02) + (random.uniform(-0.005, 0.005))
            s3_rows.append({
                "bucket_name": bucket["bucket_name"],
                "region": bucket["region"],
                "creation_date": bucket["creation_date"],
                "object_count": int(bucket["base_objects"] * growth_factor),
                "size_bytes": int(bucket["base_bytes"] * growth_factor),
                "recorded_at": timestamp,
            })

        # 3. RDS instances (stable)
        rds_rows = []
        for db in rds_base:
            rds_rows.append({
                "db_identifier": db["db_identifier"],
                "engine": db["engine"],
                "engine_version": db["engine_version"],
                "status": db["status"],
                "instance_class": db["instance_class"],
                "storage_gb": db["storage_gb"],
                "multi_az": db["multi_az"],
                "region": region,
                "recorded_at": timestamp,
            })

        # 4. IAM summary (slowly growing team)
        users = 8 + (i // 5)  # 8, 9, 10, 11, 12
        roles = 12 + (i // 3)  # 12 to 18
        iam_row = {
            "users": users,
            "groups": 3,
            "roles": roles,
            "policies": 18 + (i // 7),
            "recorded_at": timestamp,
        }

        # 5. VPCs (stable)
        vpc_rows = [
            {
                "vpc_id": vpc_id_1,
                "cidr_block": "10.0.0.0/16",
                "state": "available",
                "is_default": 0,
                "subnet_count": 4,
                "region": region,
                "recorded_at": timestamp,
            },
            {
                "vpc_id": vpc_id_2,
                "cidr_block": "172.31.0.0/16",
                "state": "available",
                "is_default": 1,
                "subnet_count": 3,
                "region": region,
                "recorded_at": timestamp,
            }
        ]

        # Store all generated resource snapshots
        tracker.store_all(ec2_rows, s3_rows, rds_rows, iam_row, vpc_rows, db_path)

        # 6. Add a successful run log
        with tracker.get_conn(db_path) as conn:
            conn.execute(
                "INSERT INTO collection_runs (started_at, finished_at, status, error_msg) VALUES (?, ?, ?, ?)",
                (timestamp, (datetime.fromisoformat(timestamp) + timedelta(seconds=2.4)).isoformat(), "success", None)
            )

    print(f"Successfully generated 21 snapshots of historical data in '{db_path}'!")


if __name__ == "__main__":
    generate_data()
