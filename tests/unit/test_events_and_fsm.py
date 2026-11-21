from collections import deque
from enum import StrEnum

import pytest

from pasr.apps.reminder.due_flow import TRANSITIONS, DueState
from pasr.orchestration.events import EventBus, EventType, PrivacyViolationError, check_payload
from pasr.orchestration.fsm import InvalidTransitionError, StateMachine
from support.clock import VirtualClock


@pytest.mark.parametrize(
    "payload",
    [{"title": "Doctor"}, {"transcript": "hi"}, {"similarity": [0.1]}, {"reason": "x" * 200}],
)
def test_event_payloads_reject_personal_content(payload):
    with pytest.raises(PrivacyViolationError):
        check_payload(payload)


def test_bus_feeds_sinks_and_survives_a_failing_sink(clock: VirtualClock):
    received = []

    def broken(event):
        raise RuntimeError("boom")

    bus = EventBus(clock, "s", sinks=[broken, received.append])
    event = bus.emit(EventType.CONSENT_ANSWERED, reminder_id=1, answer="yes")
    assert received == [event]
    assert bus.recent[-1] is event
    unsubscribe = bus.subscribe(received.append)
    unsubscribe()
    bus.emit(EventType.RUNTIME_STOPPED)
    assert len(received) == 2


class Light(StrEnum):
    RED = "RED"
    GREEN = "GREEN"
    BROKEN = "BROKEN"


def test_state_machine_validates_and_records(clock: VirtualClock):
    seen = []
    fsm = StateMachine(
        Light.RED,
        {Light.RED: {Light.GREEN}, Light.GREEN: set()},
        clock=clock,
        failure_state=Light.BROKEN,
        on_transition=seen.append,
    )
    with pytest.raises(InvalidTransitionError):
        fsm.go(Light.RED, "not allowed")
    fsm.go(Light.GREEN, "go")
    assert fsm.path() == [Light.RED, Light.GREEN]
    assert fsm.is_terminal
    with pytest.raises(InvalidTransitionError):
        fsm.go(Light.BROKEN, "terminal states cannot fail")
    assert [t.reason for t in seen] == ["go"]


def test_failure_is_reachable_from_any_active_state(clock: VirtualClock):
    fsm = StateMachine(
        Light.RED, {Light.RED: {Light.GREEN}}, clock=clock, failure_state=Light.BROKEN
    )
    fsm.go(Light.BROKEN, "error")
    assert fsm.state is Light.BROKEN


def test_due_flow_graph_is_sound():
    reachable, queue = {DueState.IDLE}, deque([DueState.IDLE])
    while queue:
        for target in TRANSITIONS[queue.popleft()]:
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
    assert reachable == set(DueState) - {DueState.FAILED}  # FAILED is entered via the failure path
    assert TRANSITIONS[DueState.DONE] == TRANSITIONS[DueState.FAILED] == frozenset()

    # every active state can still finish
    finishing = {DueState.DONE}
    changed = True
    while changed:
        changed = False
        for state, targets in TRANSITIONS.items():
            if state not in finishing and targets & finishing:
                finishing.add(state)
                changed = True
    assert finishing == set(DueState) - {DueState.FAILED}
