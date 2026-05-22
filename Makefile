.PHONY: setup setup-full mock dry-run single clean

setup:
	git submodule update --init --recursive
	uv sync
	docker pull ghcr.io/illinoisdata/theagentcompany-lite-base:latest

setup-full:
	git submodule update --init --recursive
	uv sync --extra openhands
	docker pull ghcr.io/illinoisdata/theagentcompany-lite-base:latest

mock:
	uv run python evaluation_lite/scheduler.py \
		--agent-llm-config agent --env-llm-config env \
		--mock --mock-duration 5,8 \
		--outputs-path ./outputs_mock

dry-run:
	uv run python evaluation_lite/scheduler.py \
		--agent-llm-config agent --env-llm-config env \
		--dry-run

single:
	@echo "Usage: make single TASK=gitlab-create-repo-1"
	uv run python evaluation_lite/run_eval.py \
		--task $(TASK) \
		--agent-llm-config agent --env-llm-config env \
		--server-hostname localhost \
		--outputs-path ./outputs

clean:
	rm -rf outputs outputs_mock .venv
