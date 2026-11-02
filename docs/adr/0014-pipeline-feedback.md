# 0014 , Feedback on each reminder's run, stored with the models it used

**Status:** accepted

**Context.** The thesis compares models (speaker, voice-activity, face, sensitivity) by how well
the whole pipeline behaves, not only by their similarity scores. The event log shows what the
robot did, but not whether that was right: whether someone "heard" was really there, or whether
the robot should have spoken. Only the owner, who was in the room, can say. And a run could not
be tied to the models it used: the log named a model only in the perception events, and only for
the step that ran.

**Decisions.**
- Every run logs **`flow.started`** before its first step: the speaker, VAD and face models,
  who decided the reminder is sensitive (a model's name, or `user`), the voice and face
  thresholds, the detection choice (`mode`), the policy, `sensitive` and `origin`. All are
  labels and numbers, within the log's allow-list. They come from the flow's settings snapshot,
  so a setting changed while it runs does not change what it records.
- A **run** is one reminder's flow in one session (a reminder interrupted by a restart runs
  again in the next session, as a second run). It is put together from its `flow.started`,
  `flow.state` and `reminder.delivered` events.
- The owner marks a finished run **worked well** or **did not work well** (thumbs up or down)
  and, with a thumbs down, may say **what went wrong** in their own words. On Home this is under
  the pipeline once the run has ended; on the Events page any logged run can be rated or rated
  again later, and the feedback downloaded as CSV, with one column per model.
- Feedback is stored in its own table, `pipeline_feedback` (migration 2), with a copy of the run
  (start time, last state, channel, condition), so it outlives the log's retention. Rating again
  replaces the earlier verdict.

**Consequences.**
- The comment is free text and may mention people or the reminder, so it never enters the event
  log, whose allow-list stays labels and numbers. It stays in the local database only, and is
  deleted with the log (`pasr reset --purge-log`, or the Reset page's log box), not with the
  owner, so a study's feedback survives a change of participant until the researcher purges it.
- Runs logged before `flow.started` existed can still be rated; their models show as not logged.
- A run is rated as a whole: which step went wrong lives in the comment, and in the run's
  `flow.state` events, which share its session and reminder.
