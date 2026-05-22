"""Harness interface for TheAgentCompany benchmark evaluation.

Two implementations: DockerHarness (plain Docker, custom agents) and
OpenHandsHarness (wraps OpenHands runtime, original behavior).
"""
import asyncio, json, os, subprocess, tempfile, time, logging, sys
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RED = "\033[31m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
RESET = "\033[0m"


def _truncate(s, max_len=300):
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."


def _print_event(event):
    """Print a single OpenHands event with color coding."""
    from openhands.events.action import (
        Action, MessageAction, CmdRunAction, IPythonRunCellAction,
        BrowseInteractiveAction, FileWriteAction, FileEditAction,
    )
    from openhands.events.observation import (
        Observation, CmdOutputObservation, IPythonRunCellObservation,
        BrowserOutputObservation, FileWriteObservation, FileEditObservation,
    )

    if isinstance(event, MessageAction):
        role = getattr(event, "source", "agent")
        content = _truncate(event.content or "")
        if role == "user":
            print(f"  {BLUE}[user]{RESET} {content}")
        else:
            print(f"  {CYAN}{BOLD}[thinking]{RESET} {content}")

    elif isinstance(event, CmdRunAction):
        cmd = _truncate(event.command or "")
        print(f"  {YELLOW}[action:cmd]{RESET} {cmd}")

    elif isinstance(event, CmdOutputObservation):
        out = _truncate(event.content or "")
        code = getattr(event, "exit_code", "?")
        print(f"  {DIM}[obs:cmd exit={code}]{RESET} {_truncate(out, 200)}")

    elif isinstance(event, IPythonRunCellAction):
        code = _truncate(event.code or event.content or "")
        print(f"  {YELLOW}[action:ipython]{RESET} {code}")

    elif isinstance(event, IPythonRunCellObservation):
        out = _truncate(event.content or "")
        print(f"  {DIM}[obs:ipython]{RESET} {_truncate(out, 200)}")

    elif isinstance(event, BrowseInteractiveAction):
        act = _truncate(event.browser_actions or "")
        print(f"  {MAGENTA}[action:browse]{RESET} {act}")

    elif isinstance(event, BrowserOutputObservation):
        out = _truncate(getattr(event, "agent_obs_text", "") or event.content or "")
        print(f"  {DIM}[obs:browse]{RESET} {_truncate(out, 150)}")

    elif isinstance(event, (FileWriteAction, FileEditAction)):
        path = getattr(event, "path", "?")
        content = _truncate(getattr(event, "content", "") or "")
        print(f"  {YELLOW}[action:file] {path}{RESET} {content}")

    elif isinstance(event, (FileWriteObservation, FileEditObservation)):
        out = _truncate(event.content or "")
        print(f"  {DIM}[obs:file]{RESET} {_truncate(out, 150)}")

    elif isinstance(event, Observation):
        out = _truncate(event.content or str(event))
        print(f"  {DIM}[obs]{RESET} {_truncate(out, 200)}")

    elif isinstance(event, Action):
        out = _truncate(getattr(event, "thought", "") or getattr(event, "content", "") or str(event))
        print(f"  {YELLOW}[action]{RESET} {_truncate(out, 200)}")

    sys.stdout.flush()


@dataclass
class AgentState:
    success: bool = False
    trajectory_path: str = ""
    history: list | None = None


@dataclass
class CommandResult:
    exit_code: int = 0
    content: str = ""


class BaseHarness(ABC):
    @abstractmethod
    def start(self, mount_path=None):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def run_agent(self, instruction, max_iterations=100):
        pass

    @abstractmethod
    def run_command(self, command, timeout=300) -> CommandResult:
        pass

    def setup_task_files(self, task_dir):
        pass


class DockerHarness(BaseHarness):
    """Plain Docker container harness. Subclass and override run_agent()."""

    def __init__(self, base_image="tac-base-image:latest",
                 container_name=None, network="host"):
        self.base_image = base_image
        self.container_name = container_name or f"tac-eval-{int(time.time())}"
        self.network = network
        self._mount_path = None

    def start(self, mount_path=None):
        self._mount_path = mount_path or tempfile.mkdtemp()
        os.makedirs(self._mount_path, exist_ok=True)
        subprocess.run(["docker", "run", "-d", "--name", self.container_name,
                        f"--network={self.network}",
                        "-v", f"{self._mount_path}:/outputs",
                        self.base_image, "tail", "-f", "/dev/null"],
                       check=True, capture_output=True)

    def stop(self):
        subprocess.run(["docker", "stop", self.container_name], capture_output=True)
        subprocess.run(["docker", "rm", "-f", self.container_name], capture_output=True)

    def run_command(self, command, timeout=300):
        result = subprocess.run(
            ["docker", "exec", self.container_name, "bash", "-c", command],
            capture_output=True, text=True, timeout=timeout)
        return CommandResult(exit_code=result.returncode,
                             content=result.stdout + result.stderr)

    def run_agent(self, instruction, max_iterations=100):
        raise NotImplementedError("Subclass DockerHarness and override run_agent().")


class OpenHandsHarness(BaseHarness):

    def __init__(self, base_image, llm_config=None, task_short_name="task",
                 verbose=False):
        self.base_image = base_image
        self.llm_config = llm_config
        self.task_short_name = task_short_name
        self.verbose = verbose
        self._runtime = None

    def start(self, mount_path=None):
        from openhands.core.main import create_runtime
        runtime = create_runtime(
            config=self.llm_config,
            sid=f"tac-eval-{self.task_short_name}-{int(time.time()%100000)}",
            base_container_image=self.base_image,
        )
        runtime.connect()
        self._runtime = runtime

    def stop(self):
        if self._runtime:
            try:
                self._runtime.close()
            except Exception:
                pass

    def run_command(self, command, timeout=300) -> CommandResult:
        if not self._runtime:
            return CommandResult(exit_code=1, content="Runtime not started")
        action = self._runtime.run_command(command)
        return CommandResult(exit_code=action.exit_code,
                             content=action.content)

    def run_agent(self, instruction, max_iterations=100):
        from openhands.events.action import MessageAction
        assert self._runtime is not None, "Runtime not started"
        self._runtime.send_action(MessageAction(content=instruction))
        seen = 0
        for i in range(max_iterations):
            self._runtime.step()
            state = self._runtime.get_state()
            if state and state.history and self.verbose:
                for event in state.history[seen:]:
                    try:
                        _print_event(event)
                    except Exception:
                        pass
                seen = len(state.history)
            if state and state.success:
                return state
        return state
