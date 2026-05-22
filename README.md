
<div style="text-align: center;">
  <img src="/docs/assets/logo.svg" alt="atc-lite-logo"/>
</div>

A faster, parallelized evaluation infrastructure for [TheAgentCompany](https://github.com/TheAgentCompany/TheAgentCompany) benchmarks.

**3.1 hours** instead of 17.5 hours. **4 GB** instead of 700 GB. Mock mode for 30-second infra testing.

Uses the same [OpenHands](https://github.com/All-Hands-AI/OpenHands) config and task format as upstream — just swap the runner.

See [docs/DESIGN.md](docs/DESIGN.md) for architecture and [docs/SETUP.md](docs/SETUP.md) for full setup instructions.

## Quick Start

```bash
git clone git@github.com:illinoisdata/TheAgentCompany-lite.git && cd TheAgentCompany-lite
make setup-full  # submodule + uv deps (with openhands) + docker base image
make mock        # mock benchmark (no LLM, no services needed)
make dry-run     # see execution plan
make single TASK=ds-sql-exercise   # run a single task
```

> **Note**: The first run of any task takes 10-20 minutes to build the OpenHands runtime image. Subsequent runs start in seconds.

## Configuration

LLM config uses the same `config.toml` format as upstream OpenHands. Create it in the project root:

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

`--agent-llm-config agent` maps to `[llm.agent]`, `--env-llm-config env` maps to `[llm.env]`. For mock mode, the config file is not needed.

## Install

```bash
make setup-full          # full: submodule + openhands deps + docker base image
# or:
make setup               # base only: mock mode + scheduler
```

Or manually:

```bash
git submodule update --init --recursive
uv sync --extra openhands  # requires Python >=3.12
docker pull ghcr.io/illinoisdata/theagentcompany-lite-base:latest || make build-base
```

> **Note**: If `docker pull` fails (private registry or no access), `make build-base` builds the image locally from source (~5 min first time).

## Usage

```bash
# Mock benchmark (no LLM needed)
make mock

# Specific tasks by name
make single TASK=admin-arrange-meeting-rooms

# Multiple tasks
uv run python evaluation_lite/scheduler.py \
  --agent-llm-config agent --env-llm-config env \
  --tasks "admin-arrange-meeting-rooms,pm-update-project-milestones" \
  --mock --mock-duration 5,8 --outputs-path ./outputs_mock

# Full benchmark (1 instance)
uv run python evaluation_lite/scheduler.py \
  --agent-llm-config agent --env-llm-config env \
  --server-hostname localhost --outputs-path ./outputs

# Full benchmark (6 instances)
uv run python evaluation_lite/scheduler.py \
  --agent-llm-config agent --env-llm-config env \
  --server-hostname tac_test \
  --num-instances 6 --full-stack-ids 0,4,5 \
  --outputs-path ./outputs
```

## Files

```
evaluation_lite/
  scheduler.py          # Round-based parallel scheduler
  service_manager.py    # Multi-instance port mapping and locking
  harness.py            # Docker and OpenHands harness interfaces
  run_eval.py           # Single task execution pipeline
  run_eval_mock.py      # Mock executor for infra testing
  browsing.py           # Browser automation for pre-login
```

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make setup` | Init submodule, install base deps, pull/build docker image |
| `make setup-full` | Same + openhands (Python >=3.12) |
| `make build-base` | Build base image locally (~5 min) |
| `make mock` | Run mock benchmark |
| `make dry-run` | Print execution plan |
| `make single TASK=name` | Run one task |
| `make clean` | Remove outputs and venv |
