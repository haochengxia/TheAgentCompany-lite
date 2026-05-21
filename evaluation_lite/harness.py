"""Harness interface for TheAgentCompany benchmark evaluation.

Two implementations: DockerHarness (plain Docker, custom agents) and
OpenHandsHarness (wraps OpenHands runtime, original behavior).
"""
import asyncio, json, os, subprocess, tempfile, time, logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    success: bool = False
    trajectory_path: str = ""
    history: list = None


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
    def run_command(self, command, timeout=300):
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
    """OpenHands runtime harness (original benchmark behavior)."""

    def __init__(self, base_image, llm_config=None, task_short_name="task"):
        self.base_image = base_image
        self.llm_config = llm_config
        self.task_short_name = task_short_name
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

    def run_command(self, command, timeout=300):
        if not self._runtime:
            return CommandResult(exit_code=1, content="Runtime not started")
        action = self._runtime.run_command(command)
        return CommandResult(exit_code=action.exit_code,
                             content=action.content)

    def run_agent(self, instruction, max_iterations=100):
        from openhands.events.action import MessageAction
        self._runtime.send_action(MessageAction(content=instruction))
        for _ in range(max_iterations):
            state = self._runtime.get_state()
            if state and state.success:
                return state
            self._runtime.step()
        return self._runtime.get_state()
