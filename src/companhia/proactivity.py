from collections import deque
from dataclasses import dataclass, field


@dataclass
class Proactivity:
    idle_seconds: int = 90
    interval: int = 300
    per_hour: int = 4
    mode: str = "focus"
    last_activity: float = 0
    waiting_reply: bool = False
    initiatives: deque = field(default_factory=deque)

    def activity(self, time: float):
        self.last_activity = time
        self.waiting_reply = False

    def eligible(self, time: float, busy: bool, editing: bool, has_context: bool) -> bool:
        while self.initiatives and time - self.initiatives[0] >= 3600:
            self.initiatives.popleft()
        return (
            self.mode == "company"
            and has_context
            and not busy
            and not editing
            and not self.waiting_reply
            and time - self.last_activity >= self.idle_seconds
            and len(self.initiatives) < self.per_hour
            and (not self.initiatives or time - self.initiatives[-1] >= self.interval)
        )

    def attempted(self, time: float):
        self.initiatives.append(time)

    def delivered(self):
        self.waiting_reply = True

    def started(self, time: float):
        """Compatibilidade: iniciar tentativa não significa que algo foi entregue."""
        self.attempted(time)


@dataclass
class EditingActivity:
    grace_seconds: float = 5
    last_typing: float = float("-inf")

    def typed(self, time: float):
        self.last_typing = time

    def blocked(self, time: float, draft: bool, protected: bool) -> bool:
        return draft or protected or time - self.last_typing < self.grace_seconds
