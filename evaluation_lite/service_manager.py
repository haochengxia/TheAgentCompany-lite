"""Multi-instance service manager for TheAgentCompany benchmark.

Manages N independent sets of service containers. Instance 0 is full-stack
(gitlab+rocketchat+owncloud+plane), instances beyond full_stack_count are
gitlab-only. Port offset: base + n * 10000.
"""
import threading
from dataclasses import dataclass, field
from typing import Optional

PORT_INCREMENT = 10000
BASE_PORTS = {"gitlab": 8929, "api-server": 2999, "rocketchat": 3000,
              "owncloud": 8092, "plane": 8091, "mongodb": 27017, "redis": 6379}


@dataclass
class ServiceInstance:
    instance_id: int
    project_name: str = ""
    services: list = field(default_factory=lambda: ["gitlab"])
    ports: dict = field(default_factory=dict)
    locked_by: Optional[str] = None

    def __post_init__(self):
        if not self.ports:
            self.ports = self._compute_ports()
        if not self.project_name:
            self.project_name = f"tac-inst-{self.instance_id}"

    def _compute_ports(self):
        offset = self.instance_id * PORT_INCREMENT
        return {s: b + offset for s, b in BASE_PORTS.items()}

    def get_port(self, service):
        return self.ports.get(service)


class ServiceManager:
    """Thread-safe manager for N service instances."""

    def __init__(self, num_instances=1, hostname="localhost", full_stack_ids=None):
        if full_stack_ids is None:
            full_stack_ids = [0]
        self.num_instances = num_instances
        self.hostname = hostname
        self.instances = {}
        self._lock = threading.Lock()
        for i in range(num_instances):
            svc = ["gitlab", "rocketchat", "owncloud", "plane"] if i in full_stack_ids else ["gitlab"]
            self.instances[i] = ServiceInstance(instance_id=i, services=svc)

    def acquire_instance(self, services_needed, locked_by="unknown"):
        with self._lock:
            for iid, inst in sorted(self.instances.items()):
                if inst.locked_by is not None:
                    continue
                if all(s in inst.services for s in services_needed):
                    inst.locked_by = locked_by
                    return iid
            for iid, inst in sorted(self.instances.items()):
                if all(s in inst.services for s in services_needed):
                    inst.locked_by = locked_by
                    return iid

    def release_instance(self, instance_id):
        with self._lock:
            if instance_id in self.instances:
                self.instances[instance_id].locked_by = None

    def get_connection_info(self, instance_id):
        inst = self.instances.get(instance_id)
        if inst is None:
            return None
        info = {"instance_id": instance_id, "hostname": self.hostname,
                "services": inst.services.copy()}
        info["api_port"] = inst.get_port("api-server")
        for svc in ["gitlab", "rocketchat", "owncloud", "plane"]:
            p = inst.get_port(svc)
            if p:
                info[f"{svc}_port"] = p
        return info
