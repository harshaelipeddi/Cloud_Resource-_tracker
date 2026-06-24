"""
Unit tests for Cloud Resource Tracker.
Mocks all AWS calls so no real credentials are needed.
Run: pytest tests/ -v
"""

import sqlite3
import tempfile
import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# ── Import module under test ──────────────────────────────────────────────────
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tracker


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    db = str(tmp_path / "test.db")
    tracker.init_db(db)
    return db


# ── Database tests ─────────────────────────────────────────────────────────────

def test_init_db_creates_tables(tmp_db):
    conn = sqlite3.connect(tmp_db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    expected = {"ec2_instances", "s3_buckets", "rds_instances",
                "iam_summary", "vpcs", "collection_runs"}
    assert expected.issubset(tables)


def test_store_all_inserts_rows(tmp_db):
    now = datetime.now(timezone.utc).isoformat()
    ec2 = [{
        "instance_id": "i-abc123", "name": "web", "instance_type": "t3.micro",
        "state": "running", "public_ip": "1.2.3.4", "private_ip": "10.0.0.1",
        "az": "us-east-1a", "region": "us-east-1", "launch_time": now,
        "recorded_at": now,
    }]
    s3 = [{"bucket_name": "my-bucket", "region": "us-east-1",
            "creation_date": now, "object_count": 10, "size_bytes": 1024,
            "recorded_at": now}]
    rds = [{"db_identifier": "mydb", "engine": "mysql", "engine_version": "8.0",
             "status": "available", "instance_class": "db.t3.micro",
             "storage_gb": 20, "multi_az": 0, "region": "us-east-1",
             "recorded_at": now}]
    iam = {"users": 3, "groups": 1, "roles": 5, "policies": 10, "recorded_at": now}
    vpcs = [{"vpc_id": "vpc-123", "cidr_block": "10.0.0.0/16", "state": "available",
              "is_default": 1, "subnet_count": 3, "region": "us-east-1",
              "recorded_at": now}]

    tracker.store_all(ec2, s3, rds, iam, vpcs, tmp_db)

    conn = sqlite3.connect(tmp_db)
    assert conn.execute("SELECT COUNT(*) FROM ec2_instances").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM s3_buckets").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM rds_instances").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM iam_summary").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM vpcs").fetchone()[0] == 1
    conn.close()


# ── Collector tests (mocked AWS) ──────────────────────────────────────────────

@patch("tracker.boto3.client")
def test_collect_ec2_returns_list(mock_client):
    ec2_mock = MagicMock()
    mock_client.return_value = ec2_mock

    paginator_mock = MagicMock()
    ec2_mock.get_paginator.return_value = paginator_mock
    paginator_mock.paginate.return_value = [{
        "Reservations": [{
            "Instances": [{
                "InstanceId": "i-test001",
                "InstanceType": "t3.micro",
                "State": {"Name": "running"},
                "Tags": [{"Key": "Name", "Value": "TestInstance"}],
                "PublicIpAddress": "54.0.0.1",
                "PrivateIpAddress": "10.0.1.5",
                "Placement": {"AvailabilityZone": "us-east-1a"},
                "LaunchTime": datetime(2024, 1, 1, tzinfo=timezone.utc),
            }]
        }]
    }]

    result = tracker.collect_ec2("us-east-1")
    assert len(result) == 1
    assert result[0]["instance_id"] == "i-test001"
    assert result[0]["state"] == "running"
    assert result[0]["name"] == "TestInstance"


@patch("tracker.boto3.client")
def test_collect_s3_returns_list(mock_client):
    s3_mock = MagicMock()
    cw_mock = MagicMock()

    def client_factory(service, **kwargs):
        return s3_mock if service == "s3" else cw_mock

    mock_client.side_effect = client_factory

    s3_mock.list_buckets.return_value = {
        "Buckets": [{"Name": "test-bucket",
                     "CreationDate": datetime(2023, 6, 1, tzinfo=timezone.utc)}]
    }
    s3_mock.get_bucket_location.return_value = {"LocationConstraint": "us-east-1"}
    cw_mock.get_metric_statistics.return_value = {"Datapoints": []}

    result = tracker.collect_s3()
    assert len(result) == 1
    assert result[0]["bucket_name"] == "test-bucket"


@patch("tracker.boto3.client")
def test_collect_iam_returns_dict(mock_client):
    iam_mock = MagicMock()
    mock_client.return_value = iam_mock
    iam_mock.get_account_summary.return_value = {
        "SummaryMap": {"Users": 5, "Groups": 2, "Roles": 10, "Policies": 7}
    }
    result = tracker.collect_iam()
    assert result["users"] == 5
    assert result["roles"] == 10


def test_tag_helper():
    tags = [{"Key": "Name", "Value": "web-server"}, {"Key": "Env", "Value": "prod"}]
    assert tracker._tag(tags, "Name") == "web-server"
    assert tracker._tag(tags, "Env") == "prod"
    assert tracker._tag(tags, "Missing") is None
    assert tracker._tag(None, "Name") is None
