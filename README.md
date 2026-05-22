
<div style="text-align: center;">
  <img src="/docs/assets/logo.svg" alt="atc-lite-logo"/>
</div>

A faster, parallelized evaluation infrastructure for [TheAgentCompany](https://github.com/TheAgentCompany/TheAgentCompany) benchmarks.

## What Changed

```
Original (v1):                        Lite (v2):
serial ──→ task ──→ task           Round ──→ group ──→ instance ──→ task
              │          │                 │           │           task
              ↓          ↓                 │           │
           ~17.5h      ~700GB              │           instance ──→ task
                                           │                       task
                                           group ──→ instance ──→ task
                                                     instance ──→ task
                                           group ──→ instance ──→ task
```

The original evaluation runs 175 tasks **serially**: pull image, run agent, evaluate, reset services, repeat. Each task takes ~6 min, totaling ~17.5 hours and ~700 GB of disk for task images.

The lite version introduces three key improvements:

1. **Round-based parallel scheduling** — tasks are grouped by service dependency and non-conflicting groups run concurrently. Single-instance speedup: **2.3x**.

2. **Multi-instance deployment** — run N independent service stacks (gitlab/rocketchat/owncloud/plane) and distribute large groups across instances with load balancing. 6-instance speedup: **5.7x** (~3 hours instead of ~17.5).

3. **Mock mode** — simulate task execution without LLM API calls for rapid infrastructure iteration. Full benchmark test cycle: **30 seconds** instead of hours.

### Speed Comparison

| Config | Estimated Time | Speedup | Disk |
|--------|---------------|---------|------|
| Upstream (serial) | ~17.5 h | 1.0x | ~700 GB |
| V2, 1 instance | ~7.7 h | 2.3x | shared base image |
| V2, 6 instances (3 full-stack + 3 gitlab-only) | ~3.1 h | 5.7x | shared base image |

## Architecture

See [docs/DESIGN.md](docs/DESIGN.md) for the full design rationale.

**Key idea**: Each task declares which services it needs via `dependencies.yml`. We group tasks by dependency tuple, then use graph coloring to partition groups into rounds where no two groups share a service. Within each round, groups run in parallel across available instances.

```
Dependencies → Groups → Rounds → Instance Assignment → Sequential Execution
  gitlab(47)     │          │           │                     │
  oc+rc(33)      │          │           │                     ├─ task (reset) ─→ task (reset) ─→ ...
  oc(33)         │          │           │                     │
  rc(24)         ↓          ↓           ↓                     ↓
             coloring   non-overlap  load-balanced      per-instance
             algo       rounds       split              sequential
```

## Files

| File | Lines | Purpose |
|------|-------|---------|
| `scheduler.py` | 391 | Round-based parallel scheduler: group → round → load-balance → execute |
| `service_manager.py` | 81 | Multi-instance service management (acquire/release, port mapping) |
| `harness.py` | 123 | DockerHarness (custom agents) and OpenHandsHarness (original runtime) |
| `run_eval.py` | 278 | Single task execution: init → solve → evaluate → collect results |
| `run_eval_mock.py` | 124 | Mock executor for infrastructure testing (no LLM needed) |
| `browsing.py` | 272 | Browser automation for pre-login to services (GitLab, RocketChat, etc.) |

**Total: 1269 lines**

## Quick Start

```bash
git clone git@github.com:illinoisdata/TheAgentCompany-lite.git && cd TheAgentCompany-lite

# One-command setup: submodule + uv deps + docker base image
make setup                # base (mock mode + scheduler)
# or
make setup-full           # full (includes openhands for real benchmark, requires Python >=3.12)

# Run mock benchmark (no LLM, no services needed)
make mock

# See execution plan without running
make dry-run

# Run a single task
make single TASK=admin-arrange-meeting-rooms
```

See [docs/SETUP.md](docs/SETUP.md) for full setup instructions including service deployment and multi-instance configuration.

## Usage

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Docker + Docker Compose (for real benchmark)
- TheAgentCompany services running (gitlab, rocketchat, owncloud, plane) — see [docs/SETUP.md](docs/SETUP.md)

### Install

```bash
# With uv (recommended)
uv sync                           # base: mock mode + scheduler
uv sync --extra openhands         # full: real benchmark (requires Python >=3.12)

# Without uv
pip install pyyaml
pip install openhands-ai==0.42.0  # only needed for real benchmark
```

### Mock Mode (no LLM, no services needed)

```bash
uv run python evaluation_lite/scheduler.py \
  --agent-llm-config agent --env-llm-config env \
  --mock --mock-duration 5,8 \
  --outputs-path ./outputs_mock
```

### Dry Run (see the plan)

```bash
uv run python evaluation_lite/scheduler.py \
  --agent-llm-config agent --env-llm-config env \
  --dry-run
```

### Specific Tasks

```bash
# Single task by name
uv run python evaluation_lite/run_eval.py \
  --task admin-arrange-meeting-rooms \
  --agent-llm-config agent --env-llm-config env \
  --server-hostname localhost --outputs-path ./outputs

# Multiple tasks via scheduler
uv run python evaluation_lite/scheduler.py \
  --agent-llm-config agent --env-llm-config env \
  --tasks "admin-arrange-meeting-rooms,pm-update-project-milestones" \
  --mock --mock-duration 5,8 --outputs-path ./outputs_mock
```

### Multi-Instance (6 instances)

```bash
uv run python evaluation_lite/scheduler.py \
  --agent-llm-config agent --env-llm-config env \
  --server-hostname tac_test \
  --num-instances 6 --full-stack-ids 0,4,5 \
  --outputs-path /mydata/benchmark_run
```

Instance layout:
- **Instance 0**: full stack (all services) — port base 8929
- **Instances 1–3**: gitlab-only — ports 18929, 28929, 38929
- **Instances 4–5**: full stack — ports 48929, 58929

### Custom Tasks Directory

The scheduler auto-detects tasks from `workspaces/tasks/` or `TheAgentCompany/workspaces/tasks/`. Override with:

```bash
python evaluation_lite/scheduler.py ... --tasks-dir /path/to/tasks
```

## Upstream Comparison

This project is a fork of [TheAgentCompany](https://github.com/TheAgentCompany/TheAgentCompany) with a rewritten evaluation pipeline. The upstream `evaluation/` runs tasks serially via `run_eval.sh`. Our `evaluation_lite/` adds parallel scheduling, multi-instance support, and mock mode while preserving full compatibility with the original task format and evaluators.

Key differences:
- **No task image builds** — shared base image + dynamic task file mounting (was: 175 separate images, ~700 GB)
- **Parallel scheduling** — dependency-aware round-based execution (was: serial)
- **Service reuse** — reset between tasks instead of destroy/recreate containers
- **Mock testing** — validate infrastructure without LLM costs
- **1269 lines** vs upstream 698 lines (scheduler, multi-instance, mock, browsing on top)

