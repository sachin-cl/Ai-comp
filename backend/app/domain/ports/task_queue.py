"""Task queue port — how the orchestrator schedules agent work."""
import uuid
from abc import ABC, abstractmethod


class TaskQueue(ABC):
    @abstractmethod
    async def enqueue_agent_task(self, task_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def enqueue_workflow_start(self, project_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def enqueue_embedding(self, project_id: uuid.UUID, kind: str, ref_id: uuid.UUID,
                                content: str) -> None: ...

    @abstractmethod
    async def queue_depth(self) -> int: ...
