# Design: Parallel Evaluation Infrastructure

## Problem

TheAgentCompany's original evaluation runs 175 tasks serially. Each task needs exclusive access to shared services (gitlab, rocketchat, owncloud, plane). The process for each task:

1. Pull/build task-specific Docker image (~700 GB total)
2. Start OpenHands runtime container
3. Run agent to solve task (~6 min avg)
4. Evaluate result
5. Reset services via api-server
6. Wait for services to become healthy (~2 min for gitlab)

Total: ~17.5 hours, ~700 GB disk.

## Core Idea

Each task declares its service dependencies in `dependencies.yml`. Tasks that use **different** services can run in parallel — they don't interfere. We exploit this to schedule non-conflicting tasks concurrently.

## Step 1: Group by Dependency

Walk all task directories and group by their dependency tuple:

```
("gitlab",)                              → 47 tasks
("owncloud", "rocketchat")               → 33 tasks
("owncloud",)                            → 33 tasks
("rocketchat",)                          → 24 tasks
("gitlab", "rocketchat")                 → 15 tasks
("plane",)                               →  6 tasks
("gitlab", "plane")                      →  5 tasks
("plane", "rocketchat")                  →  5 tasks
("gitlab", "owncloud")                   →  2 tasks
no deps                                  →  3 tasks
other small groups                       →  2 tasks
```

Tasks within the same group share services → **must run sequentially** (with reset between).
Tasks in different groups with no service overlap → **can run in parallel**.

## Step 2: Round Scheduling (Graph Coloring)

Partition groups into rounds using greedy graph coloring. Two groups share an edge if they have any service in common. Each round contains non-adjacent groups (no service conflicts):

```
Round 1: gitlab(47) || owncloud+rocketchat(33) || plane(6) || no-deps(3)
Round 2: owncloud(33) || rocketchat(24) || gitlab+plane(5)
Round 3: gitlab+rocketchat(15)
Round 4: plane+rocketchat(5) || gitlab+owncloud(2)
Round 5-6: remaining small groups
```

Each round is a **parallel phase**. Rounds execute sequentially.

### Why this matters

Single-instance round scheduling alone gives **2.3x speedup** because the longest group in each round dominates. Round 1 takes max(47, 33, 6, 3) × task_time = 47 tasks. Without scheduling, it would be 175 tasks.

## Step 3: Multi-Instance Split

A single service stack can only run one task at a time (services need reset between tasks). But we can run **N independent service stacks** and split large groups across them.

### Instance Layout

```
Instance 0:  full stack (gitlab + rocketchat + owncloud + plane)
Instance 1:  gitlab-only
Instance 2:  gitlab-only
Instance 3:  gitlab-only
Instance 4:  full stack
Instance 5:  full stack
```

**Why this mix:**
- Gitlab has 47+15+5+2 = 69 tasks — the biggest bottleneck. Three gitlab-only instances are cheap (~4 GB RAM each) and sufficient for pure-gitlab groups.
- Owncloud (33) and rocketchat (24) groups require full stack. Instances 4-5 handle those.
- Instance 0 is the original full stack, handles mixed groups that need all services.

### Load Balancing

`_split_groups_across_instances` distributes tasks to instances using **lightest-first round-robin**:

```python
targets.sort(key=lambda i: load.get(i, 0))  # pick least-loaded instance
for idx, tid in enumerate(targets):
    chunk = task_names[idx::len(targets)]  # round-robin split
```

For a group of 47 gitlab tasks across instances 1-5:
- Instance 1: tasks[0::5] = 10 tasks
- Instance 2: tasks[1::5] = 10 tasks
- Instance 3: tasks[2::5] = 9 tasks
- Instance 4: tasks[3::5] = 9 tasks
- Instance 5: tasks[4::5] = 9 tasks

Gitlab-only groups skip instance 0 (preserved for mixed groups), falling back if no other instance is available.

### Port Mapping

Each instance offsets ports by `n × 10000`:

| Instance | GitLab | RocketChat | OwnCloud | Plane |
|----------|--------|------------|----------|-------|
| 0 | 8929 | 3000 | 8092 | 8091 |
| 1 | 18929 | — | — | — |
| 2 | 28929 | — | — | — |
| 3 | 38929 | — | — | — |
| 4 | 48929 | 43000 | 48092 | 48091 |
| 5 | 58929 | 53000 | 58092 | 58091 |

## Step 4: Service Reset

Between tasks in the same group, services must be reset to clean state:

- **Instance 0**: HTTP POST to api-server (`/api/reset-{service}`) — original mechanism
- **Instances 1+**: `docker restart {service}-{n}` — faster, avoids api-server dependency

GitLab reset is the bottleneck (~105s: 13s docker restart + 92s wait for healthy). This is a hard constraint without modifying the Docker daemon (CRIU/ZFS snapshot approaches were tested and found insufficient).

## Mock Mode

`--mock --mock-duration 5,8` replaces LLM agent execution with random sleep (5-8s per task). This enables:

- Testing scheduler correctness without LLM costs
- Validating multi-instance deployment and load balancing
- Measuring overhead and round timing in seconds, not hours

Mock benchmark results (175 tasks, 5-8s/task):

| Instances | Time | Speedup |
|-----------|------|---------|
| 1 | 675s | 1.0x |
| 6 (3 full-stack + 3 gitlab-only) | 270s | 2.5x |

The gap between theoretical 6x and actual 2.5x comes from gitlab reset overhead (~105s per round) and uneven group sizes.

## Disk Improvement

**Original**: Each task has its own Docker image (175 images × ~4 GB = ~700 GB).

**Lite**: One shared base image with a three-stage build:

1. **Base image** (`ghcr.io/illinoisdata/theagentcompany-lite-base:latest`, ~1.2 GB) — Python 3.12 (Debian Bookworm) + common libraries + NPC setup + evaluation utilities. Contains ONBUILD directives for task files.

2. **Task image** (`tac-task-{name}:latest`, built on first run per task) — Layers task-specific files (evaluator, dependencies, task.md) on top of base image via the ONBUILD mechanism. Uses the task directory's own Dockerfile but rewrites `FROM` to point at the lite base image.

3. **Runtime image** (`tac-runtime-{name}:latest`, built on first run per task) — Layers OpenHands runtime (micromamba, poetry, playwright, chromium) on top of the task image. Cached locally after first build.

Disk usage: **~1.2 GB** for the base image + ~2.5 GB per task runtime image (cached).

## File Responsibilities

```
scheduler.py (~390 lines)
├── group_tasks_by_deps()       — read dependencies.yml, group by tuple
├── find_non_overlapping_groups() — graph coloring → rounds
├── _split_groups_across_instances() — load-balance across instances
├── run_group_sequential()      — run tasks in a group, reset between
├── _reset_services_for_group() — api-server or docker restart
└── main()                      — CLI, orchestration, ProcessPoolExecutor

service_manager.py (~80 lines)
├── ServiceInstance             — dataclass: id, services, ports, lock
└── ServiceManager              — thread-safe acquire/release/lookup

harness.py (~375 lines)
├── BaseHarness (ABC)           — interface: start/stop/run_agent/run_command
├── DockerHarness               — plain Docker, for custom agents
└── OpenHandsHarness            — wraps OpenHands 0.42.0 runtime
    ├── _build_task_image()     — build intermediate task image via ONBUILD
    ├── _build_runtime_image()  — pre-build OpenHands runtime (skip internal build)
    ├── start()                 — connect to OpenHands Docker runtime
    ├── run_agent()             — execute task via run_controller
    └── run_command()           — docker exec directly into container

run_eval.py (~392 lines)
├── load_dependencies()         — read from host or container
├── init_task_env()             — set env vars, run init.sh
├── ensure_services()           — start docker-compose services on demand
├── run_solver()                — send instruction to agent
├── run_evaluator()             — run eval.py inside container
└── main()                      — single task CLI

run_eval_mock.py (~124 lines)
└── main()                      — simulate execution with random sleep
```
