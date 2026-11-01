"""A small explicit state machine: allowed transitions are a table, every move is recorded."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pasr.orchestration.clock import Clock


class InvalidTransitionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Transition[S: StrEnum]:
    source: S
    target: S
    reason: str
    at: datetime


class StateMachine[S: StrEnum]:
    def __init__(
        self,
        initial: S,
        transitions: Mapping[S, Collection[S]],
        *,
        clock: Clock,
        failure_state: S | None = None,
        on_transition: Callable[[Transition[S]], None] | None = None,
    ) -> None:
        self.state = initial
        self.transitions = transitions
        self.clock = clock
        self.failure_state = failure_state
        self.on_transition = on_transition
        self.history: list[Transition[S]] = []

    @property
    def is_terminal(self) -> bool:
        return not self.transitions.get(self.state)

    def can_go(self, target: S) -> bool:
        if target == self.failure_state:
            return not self.is_terminal
        return target in self.transitions.get(self.state, ())

    def go(self, target: S, reason: str) -> None:
        if not self.can_go(target):
            raise InvalidTransitionError(f"{self.state} → {target} is not allowed")
        transition = Transition(self.state, target, reason, self.clock.now())
        self.state = target
        self.history.append(transition)
        if self.on_transition is not None:
            self.on_transition(transition)

    def path(self) -> list[S]:
        if not self.history:
            return [self.state]
        return [self.history[0].source, *(t.target for t in self.history)]
