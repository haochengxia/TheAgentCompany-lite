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
python3 --version         # 3.12+ (required by OpenHands)

# uv (package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### LLM API Keys

You need two LLM configs (can point to the same model):

- **Agent LLM**: the model that solves tasks
- **Environment LLM**: used by NPCs and evaluators (typically a cheaper model)

Create `config.toml` in the project root:

```toml
[llm.agent]
model = "gpt-4o-mini"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."

[llm.env]
model = "gpt-4o-mini"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."
```

`config.toml` is gitignored — your API keys stay local.

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

### Verify Services

```bash
for svc in gitlab rocketchat owncloud plane; do
    curl -s -o /dev/null -w "$svc: %{http_code}\n" localhost:2999/api/healthcheck/$svc
done
# Expected: all return 200
```

### Service URLs & Credentials

| Service | URL | Username | Password |
|---------|-----|----------|----------|
| GitLab | http://the-agent-company.com:8929 | `root` | `theagentcompany` |
| RocketChat | http://the-agent-company.com:3000 | `theagentcompany` | `theagentcompany` |
| ownCloud | http://the-agent-company.com:8092 | `theagentcompany` | `theagentcompany` |
| Plane | http://the-agent-company.com:8091 | `agent@company.com` | `theagentcompany` |

### Remote Server Setup

If services run on a remote machine:

```bash
# On the remote server
echo "<server-ip> the-agent-company.com" | sudo tee -a /etc/hosts

# On your local machine (if you want browser access)
echo "<server-ip> the-agent-company.com" | sudo tee -a /etc/hosts
```

---

## 3. Evaluation Environment

### One-Line Setup

```bash
git clone git@github.com:illinoisdata/TheAgentCompany-lite.git && cd TheAgentCompany-lite
make setup-full    # submodule + uv deps (with openhands) + docker base image
```

Or step by step:

```bash
git submodule update --init --recursive
uv sync --extra openhands    # requires Python >=3.12
docker pull ghcr.io/illinoisdata/theagentcompany-lite-base:latest
```

### Verify Setup

```bash
# Check tasks are available
python3 -c "
from pathlib import Path
tasks = Path('TheAgentCompany/workspaces/tasks')
print(f'Tasks exist: {tasks.exists()}')
print(f'Task count: {sum(1 for d in tasks.iterdir() if d.is_dir()) if tasks.exists() else 0}')
"
# Expected: Tasks exist: True, Task count: 175
```

### Image Build (Automatic)

On first run, the harness automatically builds two images per task:

1. **Task image**: layers task files (evaluator, task.md) onto the base image. Takes ~5 seconds.
2. **Runtime image**: layers OpenHands runtime (micromamba, poetry, playwright, chromium). Takes **10-20 minutes on first run**, then cached.

Subsequent runs of the same task reuse the cached images instantly.

---

## 4. Mock Benchmark (Quick Validation)

Mock mode simulates task execution without LLM calls. Use this to verify your infrastructure before spending money on real benchmarks.

```bash
make mock
# or:
uv run python evaluation_lite/scheduler.py \
    --agent-llm-config agent \
    --env-llm-config env \
    --mock --mock-duration 5,8 \
    --outputs-path ./outputs_mock
```

> **Note**: Mock mode does NOT require services to be running. It only simulates timing.

### Mock with Multiple Instances

```bash
uv run python evaluation_lite/scheduler.py \
    --agent-llm-config agent \
    --env-llm-config env \
    --mock --mock-duration 5,8 \
    --num-instances 6 --full-stack-ids 0,4,5 \
    --outputs-path ./outputs_mock
```

---

## 5. Single-Instance Benchmark

The simplest real benchmark. All tasks run on one service stack.

### Prerequisites

- [x] Services running (Section 2)
- [x] Environment set up (Section 3)
- [x] LLM API keys in `config.toml`

### Dry Run First

```bash
make dry-run
# or:
uv run python evaluation_lite/scheduler.py \
    --agent-llm-config agent \
    --env-llm-config env \
    --server-hostname localhost \
    --dry-run
```

This prints the execution plan without running anything.

### Run a Single Task

```bash
make single TASK=ds-sql-exercise
# or:
uv run python evaluation_lite/run_eval.py \
    --task ds-sql-exercise \
    --agent-llm-config agent --env-llm-config env \
    --server-hostname localhost \
    --verbose \
    --outputs-path ./outputs
```

The first run of any task takes 10-20 minutes to build the runtime image. Subsequent runs start in seconds.

### Run Full Benchmark

```bash
uv run python evaluation_lite/scheduler.py \
    --agent-llm-config agent \
    --env-llm-config env \
    --server-hostname localhost \
    --outputs-path ./outputs
```

### Monitor Progress

The scheduler prints real-time progress:
```
  [gitlab] [1/47] gitlab-create-repo-1: RUNNING...
  [gitlab] [1/47] gitlab-create-repo-1: OK (342.1s)
  ...
  Progress: 47/175 (26%) | 8.2 tasks/min | ETA: 15 min
```

Results are saved incrementally. If the run crashes, re-running will skip tasks that already have results.

---

## 6. Multi-Instance Benchmark

Distributes tasks across N independent service stacks for parallelism.

### When to Use

- 6+ instances when you need ~3h instead of ~8h
- Requires enough RAM (~6-7 GB per full-stack instance, ~4 GB per gitlab-only instance)

### Run

```bash
uv run python evaluation_lite/scheduler.py \
    --agent-llm-config agent \
    --env-llm-config env \
    --server-hostname localhost \
    --num-instances 6 \
    --full-stack-ids 0,4,5 \
    --outputs-path ./outputs
```

This assumes you've already deployed instances 1-5 (see Section 7). The scheduler will:
1. Assign gitlab-only groups to instances 1-5 (skipping instance 0)
2. Assign full-stack groups to instances 0, 4, 5
3. Round-robin split large groups across matching instances

---

## 7. Multi-Instance Service Deployment

Each instance is an independent set of service containers.

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

### Deploy GitLab-Only Instances (1-3)

```bash
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
```

### Full-Stack Instance Template (Instance 4)

```yaml
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
bash run_eval.sh \
    --agent-llm-config agent \
    --env-llm-config env \
    --server-hostname localhost \
    --outputs-path /mydata/upstream_baseline
```

This takes ~17.5 hours. It pulls 175 task images (~700 GB) and runs them serially.

### Step 2: Run Lite

```bash
uv run python evaluation_lite/scheduler.py \
    --agent-llm-config agent \
    --env-llm-config env \
    --server-hostname localhost \
    --outputs-path /mydata/lite_1inst
```

### Step 3: Compare Results

```bash
python3 -c "
import json

def summarize(path, label):
    with open(f'{path}/summary.json') as f:
        d = json.load(f)
    hrs = d['duration_seconds'] / 3600
    print(f'{label}: {d[\"passed\"]} passed, {d[\"failed\"]} failed, {hrs:.1f} hours')

summarize('/mydata/upstream_baseline', 'Upstream')
summarize('/mydata/lite_1inst', 'Lite')
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

### First run is slow (10-20 minutes per task)

Expected on first run. The OpenHands runtime image (micromamba + poetry + playwright + chromium) is built once per task and cached locally. Subsequent runs start in seconds.

### Services won't start

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker logs gitlab --tail 50

# Common fix: remove stale containers and restart
docker compose -p theagentcompany down
bash setup.sh
```

### GitLab takes forever to start

GitLab typically takes 2-3 minutes. If longer:

```bash
docker logs gitlab --tail 100
curl -v http://the-agent-company.com:8929/
echo "127.0.0.1 the-agent-company.com" | sudo tee -a /etc/hosts
```

### "No module named 'openhands'"

```bash
uv sync --extra openhands    # not: pip install openhands-ai
```

### Runtime image build fails

If the OpenHands runtime build fails (e.g., network timeout), remove the cached image and retry:

```bash
docker rmi tac-runtime-{task-name}:latest
# Re-run the task — it will rebuild
```

### Disk space

Runtime images use ~2.5 GB each. Clean up:

```bash
docker image prune -af    # remove all unused images
```

### Port conflicts

```bash
sudo lsof -i :8929
docker stop $(docker ps -q --filter "publish=8929")
```

### Mock mode hangs

```bash
pkill -f run_eval_mock
uv run python evaluation_lite/scheduler.py \
    --agent-llm-config agent --env-llm-config env \
    --mock --mock-duration 2,3 \
    --outputs-path /tmp/mock_debug
```
