# Cloud Resource Tracker

> **Python + SQLite + Grafana** — Collects AWS resource metrics on a schedule and visualises them in a live Grafana dashboard.

---

## Architecture

```
AWS APIs (EC2 · S3 · RDS · IAM · VPC)
          │
          ▼
   tracker.py  (boto3 collector)
          │
          ▼
  cloud_resources.db  (SQLite — WAL mode)
          │
          ▼
  Grafana + SQLite plugin  →  Dashboard at http://localhost:3000
```

---

## Features

| Feature | Detail |
|---|---|
| **AWS Resources** | EC2, S3, RDS, IAM, VPC |
| **Storage** | SQLite with WAL mode for concurrent reads |
| **Visualisation** | Grafana 10 with pre-built dashboard (auto-provisioned) |
| **Scheduling** | Cron script or Jenkins pipeline |
| **Containerised** | Docker + Docker Compose |
| **Tested** | pytest unit tests with mocked AWS calls |
| **Logging** | Structured logs to stdout + `tracker.log` |

---

## Quick Start

### 1 — Clone and configure

```bash
git clone https://github.com/<your-username>/cloud-resource-tracker.git
cd cloud-resource-tracker
cp .env.example .env
# Edit .env — add your AWS credentials and Grafana password
```

### 2 — Run with Docker Compose

```bash
# Start Grafana
docker-compose up -d grafana

# Run a collection immediately
docker-compose run --rm tracker
```

Visit **http://localhost:3000** — log in with credentials from your `.env`.
The **Cloud Resource Tracker** dashboard loads automatically.

### 3 — Schedule automatic collections (every 15 minutes)

```bash
bash scripts/schedule_tracker.sh
```

---

## Running without Docker

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1

python tracker.py
```

---

## AWS IAM Permissions Required

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "s3:ListAllMyBuckets",
        "s3:GetBucketLocation",
        "rds:DescribeDBInstances",
        "iam:GetAccountSummary",
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Project Structure

```
cloud_resource_tracker/
├── tracker.py                          # Main collector script
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example                        # Copy to .env
├── .gitignore
│
├── sql/
│   └── grafana_queries.sql             # All 12 Grafana panel queries
│
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── sqlite.yml              # Auto-configures SQLite datasource
│       └── dashboards/
│           ├── dashboard.yml           # Grafana provisioning config
│           └── cloud_tracker.json      # Pre-built dashboard (12 panels)
│
├── scripts/
│   └── schedule_tracker.sh            # Installs cron job
│
├── tests/
│   └── test_tracker.py                # Mocked unit tests
│
└── README.md
```

---

## Dashboard Panels

| # | Panel | Type |
|---|---|---|
| 1 | EC2 Instance Count | Stat |
| 2 | S3 Bucket Count | Stat |
| 3 | RDS Instance Count | Stat |
| 4 | VPC Count | Stat |
| 5 | EC2 States | Pie chart |
| 6 | RDS Engines | Pie chart |
| 7 | VPC Overview | Table |
| 8 | Collection Run History | Table |

---

## Tech  Stack

- **Python 3.11** + **boto3** — AWS data collection
- **SQLite** (WAL mode) — lightweight time-series storage
- **Grafana 10** + `frser-sqlite-datasource` — visualisation
- **Docker / Docker Compose** — containerised deployment

---

*Built by Elipeddi Harshavardhan*
