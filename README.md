
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

## Usage

### Prerequisites

- Docker + Docker Compose
- TheAgentCompany services running (gitlab, rocketchat, owncloud, plane)
- Python 3.10+ with `pyyaml`

### Dry Run (see the plan without executing)

```bash
python evaluation_lite/scheduler.py \
  --agent-llm-config agent \
  --env-llm-config env \
  --dry-run
```

### Mock Mode (infrastructure testing, no LLM)

```bash
python evaluation_lite/scheduler.py \
  --agent-llm-config agent \
  --env-llm-config env \
  --mock --mock-duration 5,8 \
  --outputs-path /mydata/mock_test
```

### Multi-Instance (6 instances)

```bash
python evaluation_lite/scheduler.py \
  --agent-llm-config agent \
  --env-llm-config env \
  --server-hostname tac_test \
  --num-instances 6 \
  --full-stack-ids 0,4,5 \
  --outputs-path /mydata/benchmark_run
```

Instance layout:
- **Instance 0**: full stack (all services) — port base 8929
- **Instances 1–3**: gitlab-only — ports 18929, 28929, 38929
- **Instances 4–5**: full stack — ports 48929, 58929

### Single Task (debugging)

```bash
python evaluation_lite/run_eval.py \
  --task-dir workspaces/tasks/gitlab-create-repo-1 \
  --agent-llm-config agent \
  --env-llm-config env \
  --server-hostname localhost \
  --outputs-path ./outputs
```

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
- **980 lines** vs upstream 698 lines (but with scheduler, multi-instance, mock on top)

