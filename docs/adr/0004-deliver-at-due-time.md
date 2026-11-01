# 0004 , Deliver at the due time on both channels

**Status:** accepted (M0)

**Context.** For sensitive reminders the robot wakes up early (7 minutes by default) to check
for bystanders and ask for consent. The owner may answer the watch several minutes before the
reminder is due.

**Decision.** After the decision, the flow waits in `WAIT_FOR_DUE` and delivers at the due time,
whether the channel is speech or the watch. The path for "owner said no" is therefore
`… → AWAITING_CONSENT → WAIT_FOR_DUE → DISCLOSE_WATCH → DONE`.

**Consequences.** A reminder always arrives when it is due, never early. A bystander who arrives
between the check and the due time is not detected. That is a known limitation;
`reminder.listen_until_due` narrows the gap by listening right up to the due time.
