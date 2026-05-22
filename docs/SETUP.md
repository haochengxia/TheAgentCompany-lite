# Setup & Running Guide

This guide walks through everything needed to run the lite evaluation, from a fresh machine to a full benchmark.

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Server Setup (services)](#2-server-setup-services)
3. [Evaluation Environment](#3-evaluation-environment)
4. [Mock Benchmark (quick validation)](#4-mock-benchmark-quick-validation)
5. [Single-Instance Benchmark](#5-single-instance-benchmark)
6. [Multi-Instance Benchmark](#6-multi-instance-benchmark)
7. [Multi-Instance Service Deployment](#7-multi-instance-service-deployment)
8. [Comparison Experiment: Upstream vs Lite](#8-comparison-experiment-upstream-vs-lite)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Prerequisites

### Hardware

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores | 16+ cores |
| RAM | 16 GB | 64 GB (6-instance: ~33 GB for services) |
| Disk | 50 GB | 200 GB+ SSD |
| Network | — | Stable connection to LLM API |

### Software

```bash
# Docker (required)
docker --version          # 24+
docker compose version    # v2+

# Python (required)
python3 --version         # 3.10+

# Poetry (for upstream baseline only)
poetry --version          # 1.7+

# SSH access (if server runs on a remote machine)
ssh your-server-hostname
```

### Python Dependencies

```bash
pip install pyyaml        # Required for scheduler and run_eval
pip install openhands-ai==0.42.0  # Required only for OpenHands harness
```

### LLM API Keys

You need two LLM configs (can point to the same model):

- **Agent LLM**: the model that solves tasks
- **Environment LLM**: used by NPCs and evaluators (typically a cheaper model)

Set up in OpenHands `config.toml`:
```toml
[llm.agent]
api_key = "your-api-key"
model = "gpt-4o-mini"
base_url = "https://api.openai.com/v1"    # or your proxy

[llm.env]
api_key = "your-api-key"
model = "gpt-4o-mini"
base_url = "https://api.openai.com/v1"
```

---

## 2. Server Setup (Services)

The evaluation needs four web services running: GitLab, RocketChat, ownCloud, and Plane. Plus an api-server that manages service resets.

### Quick Start (Single Machine)

```bash
cd TheAgentCompany/servers

# 1. Point the domain to localhost
echo "127.0.0.1 the-agent-company.com" | sudo tee -a /etc/hosts

# 2. Set the GitLab port (default: 8929)
export GITLAB_PORT=8929

# 3. Pull all images and start services
bash setup.sh
```

`setup.sh` pulls ~15 Docker images, starts the api-server on port 2999, and waits for all services to become healthy (~2-3 minutes for GitLab).

### Manual Step-by-Step

If `setup.sh` doesn't work for your environment:

```bash
cd TheAgentCompany/servers

# Start core services via docker compose
GITLAB_PORT=8929 docker compose -p theagentcompany up -d

# Start Plane (separate compose)
make init HOSTNAME=localhost
make start-plane

# Start RocketChat NPC data population
make start-rocketchat

# Start Redis for sotopia NPCs
make start-sotopia-redis

# Start the api-server (manages resets)
docker run -d \
    --name api-server \
    --network host \
    --restart always \
    -v /var/run/docker.sock:/var/run/docker.sock \
    ghcr.io/theagentcompany/servers-api-server:1.0.0
```

### Verify Services

```bash
# Check all services via api-server
for svc in gitlab rocketchat owncloud plane; do
    curl -s -o /dev/null -w "$svc: %{http_code}\n" localhost:2999/api/healthcheck/$svc
done

# Expected output:
# gitlab: 200
# rocketchat: 200
# owncloud: 200
# plane: 200
```

If any service returns non-200, check `docker ps` for crashed containers and `docker logs <container>` for errors.

### Service URLs & Credentials

| Service | URL | Username | Password |
|---------|-----|----------|----------|
| GitLab | http://the-agent-company.com:8929 | `root` | `theagentcompany` |
| RocketChat | http://the-agent-company.com:3000 | `theagentcompany` | `theagentcompany` |
| ownCloud | http://the-agent-company.com:8092 | `theagentcompany` | `theagentcompany` |
| Plane | http://the-agent-company.com:8091 | `agent@company.com` | `theagentcompany` |
| api-server | http://localhost:2999 | — | — |

### Remote Server Setup

If you're running services on a remote machine (e.g., `tac_test`):

```bash
# On the remote server
echo "<server-ip> the-agent-company.com" | sudo tee -a /etc/hosts

# On your local machine (if you want browser access)
echo "<server-ip> the-agent-company.com" | sudo tee -a /etc/hosts
```

---

## 3. Evaluation Environment

### Prepare Workspace

The scheduler reads tasks from `TheAgentCompany/workspaces/tasks/`. Ensure the submodule is initialized:

```bash
cd TheAgentCompany-lite
git submodule update --init --recursive
```

### Build the Base Image

The lite evaluation uses a single shared base image instead of 175 task-specific images:

```bash
cd TheAgentCompany/workspaces/base_image
docker build -t tac-base-image:latest .
```

This image contains:
- Python 3.12 + common libraries
- NPC setup (rocketchat API, sotopia, litellm)
- Evaluation utilities (`/utils/eval.py`, `/utils/init.sh`, etc.)

Task-specific files (`task.md`, `evaluator.py`, `dependencies.yml`) are mounted at runtime.

### Verify Python Path

```bash
# The scheduler resolves TASKS_DIR relative to evaluation_lite/
python3 -c "
from pathlib import Path
tasks = Path('TheAgentCompany/workspaces/tasks')
print(f'Tasks exist: {tasks.exists()}')
print(f'Task count: {sum(1 for d in tasks.iterdir() if d.is_dir()) if tasks.exists() else 0}')
"
# Expected: Tasks exist: True, Task count: 175
```

---

## 4. Mock Benchmark (Quick Validation)

Mock mode simulates task execution without LLM calls. Use this to verify your infrastructure before spending money on real benchmarks.

```bash
python3 evaluation_lite/scheduler.py \
    --agent-llm-config agent \
    --env-llm-config env \
    --mock --mock-duration 5,8 \
    --outputs-path /tmp/mock_test
```

Expected output:
```
============================================================
TheAgentCompany V2 - Smart Parallel Scheduler
============================================================
Total tasks: 175, Groups: 14

Execution Plan:
  Round 1/6: gitlab(47) || owncloud+rocketchat(33) || plane(6) || no-deps(3)
  Round 2/6: owncloud(33) || rocketchat(24) || gitlab+plane(5)
  Round 3/6: gitlab+rocketchat(15)
  Round 4/6: plane+rocketchat(5) || gitlab+owncloud(2)
  ...

MOCK MODE: simulating 5-8s per task
...
COMPLETE: X passed, Y failed
Total: X.X min (XXXs)
```

### Mock with Multiple Instances

```bash
python3 evaluation_lite/scheduler.py \
    --agent-llm-config agent \
    --env-llm-config env \
    --mock --mock-duration 5,8 \
    --num-instances 6 --full-stack-ids 0,4,5 \
    --outputs-path /tmp/mock_6inst
```

> **Note**: Mock mode does NOT require services to be running. It only simulates timing.

---

## 5. Single-Instance Benchmark

This is the simplest real benchmark. All tasks run on one service stack.

### Prerequisites

- [x] Services running (Section 2)
- [x] Base image built (Section 3)
- [x] LLM API keys configured

### Dry Run First

```bash
python3 evaluation_lite/scheduler.py \
    --agent-llm-config agent \
    --env-llm-config env \
    --server-hostname localhost \
    --dry-run
```

This prints the execution plan without running anything. Verify the round/group assignments look correct.

### Run

```bash
python3 evaluation_lite/scheduler.py \
    --agent-llm-config agent \
    --env-llm-config env \
    --server-hostname localhost \
    --outputs-path /mydata/benchmark_1inst
```

### Monitor Progress

The scheduler prints real-time progress:
```
  [gitlab] [1/47] gitlab-create-repo-1: RUNNING...
  [gitlab] [1/47] gitlab-create-repo-1: OK (342.1s)
  ...
  Progress: 47/175 (26%) | 8.2 tasks/min | ETA: 15 min
```

Results are saved incrementally. If the run crashes, re-running will skip tasks that already have `eval_*.json` results.

---

## 6. Multi-Instance Benchmark

Distributes tasks across N independent service stacks for parallelism.

### When to Use

- 6+ instances when you need ~3h instead of ~8h
- Requires enough RAM (~6-7 GB per full-stack instance, ~4 GB per gitlab-only instance)

### Run

```bash
python3 evaluation_lite/scheduler.py \
    --agent-llm-config agent \
    --env-llm-config env \
    --server-hostname localhost \
    --num-instances 6 \
    --full-stack-ids 0,4,5 \
    --outputs-path /mydata/benchmark_6inst
```

This assumes you've already deployed instances 1-5 (see Section 7). The scheduler will:
1. Assign gitlab-only groups to instances 1-5 (skipping instance 0)
2. Assign full-stack groups to instances 0, 4, 5
3. Round-robin split large groups across matching instances

---

## 7. Multi-Instance Service Deployment

Each instance is an independent set of service containers. You need to create docker-compose configs for instances 1-5.

### Instance Layout

| Instance | Type | GitLab Port | RC Port | OC Port | Plane Port | RAM |
|----------|------|-------------|---------|---------|------------|-----|
| 0 | Full stack | 8929 | 3000 | 8092 | 8091 | ~7 GB |
| 1 | GitLab-only | 18929 | — | — | — | ~4 GB |
| 2 | GitLab-only | 28929 | — | — | — | ~4 GB |
| 3 | GitLab-only | 38929 | — | — | — | ~4 GB |
| 4 | Full stack | 48929 | 43000 | 48092 | 48091 | ~7 GB |
| 5 | Full stack | 58929 | 53000 | 58092 | 58091 | ~7 GB |

**Total RAM: ~33 GB**

### Deploy Script

Create a deployment script or use this manual approach:

```bash
# Instance 0: already running from setup.sh (full stack on default ports)

# For instances 1-3 (gitlab-only):
for i in 1 2 3; do
    port=$((8929 + i * 10000))
    mkdir -p /tmp/tac-inst-$i
    cat > /tmp/tac-inst-$i/docker-compose.yml <<EOF
services:
  gitlab:
    image: ghcr.io/theagentcompany/servers-gitlab:1.0.0
    container_name: gitlab-$i
    restart: always
    hostname: the-agent-company.com
    environment:
      GITLAB_OMNIBUS_CONFIG: |
        external_url 'http://the-agent-company.com:$port'
        gitlab_rails['gitlab_shell_ssh_port'] = 2424
    ports:
      - "$port:8929"
    shm_size: '256m'
EOF
    docker compose -p tac-inst-$i -f /tmp/tac-inst-$i/docker-compose.yml up -d
done

# For instances 4-5 (full stack), you need all services:
# Copy the original docker-compose.yml and adjust ALL port mappings.
# This is more involved — see the template below.
```

### Full-Stack Instance Template (Instance 4)

```yaml
# /tmp/tac-inst-4/docker-compose.yml
services:
  gitlab:
    image: ghcr.io/theagentcompany/servers-gitlab:1.0.0
    container_name: gitlab-4
    restart: always
    hostname: the-agent-company.com
    environment:
      GITLAB_OMNIBUS_CONFIG: |
        external_url 'http://the-agent-company.com:48929'
        gitlab_rails['gitlab_shell_ssh_port'] = 2424
    ports:
      - "48929:8929"
    shm_size: '256m'

  owncloud:
    image: ghcr.io/theagentcompany/servers-owncloud:1.0.0
    container_name: owncloud-4
    restart: always
    ports:
      - "48092:80"
    environment:
      - OWNCLOUD_DOMAIN=the-agent-company.com:48092
      - OWNCLOUD_TRUSTED_DOMAINS=localhost,the-agent-company.com:48092
      - OWNCLOUD_ADMIN_USERNAME=theagentcompany
      - OWNCLOUD_ADMIN_PASSWORD=theagentcompany
    extra_hosts:
      - "the-agent-company.com:host-gateway"

  owncloud-collabora:
    image: collabora/code:24.04.9.2.1
    container_name: owncloud-collabora-4
    restart: always
    ports:
      - "49980:9980"
    environment:
      - extra_params=--o:ssl.enable=false
    extra_hosts:
      - "the-agent-company.com:host-gateway"

  rocketchat:
    image: registry.rocket.chat/rocketchat/rocket.chat:5.3.0
    container_name: rocketchat-4
    restart: always
    extra_hosts:
      - "the-agent-company.com:host-gateway"
    environment:
      ADMIN_USERNAME: theagentcompany
      ADMIN_PASS: theagentcompany
      ADMIN_EMAIL: theagentcompany@example.com
      ADMIN_NAME: theagentcompany
      Show_Setup_Wizard: completed
      OVERWRITE_SETTING_Show_Setup_Wizard: completed
      MONGO_URL: "mongodb://mongodb-4:27017/rocketchat?replicaSet=rs0"
      MONGO_OPLOG_URL: "mongodb://mongodb-4:27017/local?replicaSet=rs0"
      ROOT_URL: http://the-agent-company.com:43000
      PORT: 3000
    depends_on:
      - mongodb
    ports:
      - "43000:3000"

  mongodb:
    image: bitnamilegacy/mongodb:5.0
    container_name: rocketchat-mongodb-4
    restart: always
    environment:
      - MONGODB_REPLICA_SET_MODE=primary
      - MONGODB_REPLICA_SET_NAME=rs0
      - MONGODB_PORT_NUMBER=27017
    volumes:
      - mongodb_data_4:/bitnami/mongodb

  redis-stack:
    image: redis/redis-stack-server:7.4.0-v0
    container_name: redis-stack-4
    restart: always
    ports:
      - "46379:6379"
    environment:
      - REDIS_ARGS=--requirepass theagentcompany --user theagentcompany on >theagentcompany ~* &* +@all

volumes:
  mongodb_data_4:
```

### Verify All Instances

```bash
# Check gitlab instances are healthy
for i in 0 1 2 3 4 5; do
    port=$((8929 + i * 10000))
    curl -s -o /dev/null -w "Instance $i gitlab:$port → %{http_code}\n" \
         http://the-agent-company.com:$port/ 2>/dev/null || echo "Instance $i: FAILED"
done
```

---

## 8. Comparison Experiment: Upstream vs Lite

To produce a fair comparison, run both evaluations with the same LLM config on the same hardware.

### Step 1: Run Upstream Baseline

```bash
cd TheAgentCompany/evaluation

# The upstream runs tasks serially using task images
bash run_eval.sh \
    --agent-llm-config agent \
    --env-llm-config env \
    --server-hostname localhost \
    --outputs-path /mydata/upstream_baseline
```

This takes ~17.5 hours. It pulls 175 task images (~700 GB) and runs them serially.

### Step 2: Run Lite (Single Instance)

```bash
python3 evaluation_lite/scheduler.py \
    --agent-llm-config agent \
    --env-llm-config env \
    --server-hostname localhost \
    --outputs-path /mydata/lite_1inst
```

### Step 3: Run Lite (Multi-Instance)

```bash
python3 evaluation_lite/scheduler.py \
    --agent-llm-config agent \
    --env-llm-config env \
    --server-hostname localhost \
    --num-instances 6 --full-stack-ids 0,4,5 \
    --outputs-path /mydata/lite_6inst
```

### Step 4: Compare Results

```bash
python3 -c "
import json

def summarize(path, label):
    with open(f'{path}/summary.json') as f:
        d = json.load(f)
    hrs = d['duration_seconds'] / 3600
    print(f'{label}: {d[\"passed\"]} passed, {d[\"failed\"]} failed, {hrs:.1f} hours')

summarize('/mydata/upstream_baseline', 'Upstream')
summarize('/mydata/lite_1inst', 'Lite 1-inst')
summarize('/mydata/lite_6inst', 'Lite 6-inst')
"
```

### Fairness Checklist

- [ ] Same LLM model and API endpoint for all runs
- [ ] Same server hostname (same service stack)
- [ ] Same task set (all 175 tasks)
- [ ] Reset services between runs (fresh state)
- [ ] Record start/end timestamps for reproducibility

---

## 9. Troubleshooting

### Services won't start

```bash
# Check what's running
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Check logs for a specific service
docker logs gitlab --tail 50
docker logs api-server --tail 50

# Common fix: remove stale containers and restart
docker compose -p theagentcompany down
bash setup.sh
```

### GitLab takes forever to start

GitLab typically takes 2-3 minutes. If it takes longer than 5 minutes:

```bash
# Check GitLab logs
docker logs gitlab --tail 100

# Ensure hostname resolution works
curl -v http://the-agent-company.com:8929/

# If "the-agent-company.com" doesn't resolve:
echo "127.0.0.1 the-agent-company.com" | sudo tee -a /etc/hosts
```

### Task fails with "PermissionError" on output directory

The evaluation creates files as root inside Docker containers. If you can't clean up:

```bash
sudo rm -rf /mydata/benchmark_run/.tmp_*
```

The scheduler handles this automatically with `shutil.rmtree` fallback to `sudo rm`.

### Port conflicts

If you see "port is already allocated":

```bash
# Find what's using the port
sudo lsof -i :8929
# or
ss -tlnp | grep 8929

# Stop conflicting containers
docker stop $(docker ps -q --filter "publish=8929")
```

### Mock mode hangs

Mock mode should complete in ~5-10 minutes. If it hangs:

```bash
# Check for zombie processes
ps aux | grep run_eval_mock

# Kill stale processes
pkill -f run_eval_mock

# Re-run with verbose output
python3 evaluation_lite/scheduler.py \
    --agent-llm-config agent --env-llm-config env \
    --mock --mock-duration 2,3 \
    --outputs-path /tmp/mock_debug
```

### OpenHands import errors

If you see `ModuleNotFoundError: No module named 'openhands'`:

```bash
# OpenHands is only needed for the real (non-mock) benchmark
pip install openhands-ai==0.42.0

# Or use poetry (upstream's package manager)
cd TheAgentCompany
poetry install --only evaluation
```
