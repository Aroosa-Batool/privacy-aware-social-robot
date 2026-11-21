# 0003 , Fail closed

**Status:** accepted (M0)

**Context.** Detection can fail: models crash, the owner may not be enrolled, devices disconnect,
or the owner does not answer the watch.

**Decision.** Whenever the robot cannot establish that disclosure is allowed, it does not speak.
Errors move the flow to `FAILED` and the reminder goes to the watch at its due time. An
unanswered consent prompt is treated as *no* for that reminder and is never remembered.

**Consequences.** The owner may occasionally receive a reminder on the watch that could safely
have been spoken. The event log records `flow.error` with the exception type so researchers can
measure how often this happens.
