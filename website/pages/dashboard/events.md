---
title: Events
description: The research log, on the dashboard. Every state change, detection score and consent answer, as labels and numbers only.
---

The log never holds reminder titles, transcripts, embeddings or images: `EventBus.emit` accepts
only allow-listed keys with short values and raises otherwise.

::image src=/assets/media/events.webp alt="The Events page: session, event type and row filters, a bar chart of event counts per type, and a table of events." url=localhost:8501/events caption="Counts per event type for the selected rows, above the events themselves."

## Filter

| Control | Use |
|---|---|
| **Session** | One run of the robot (`run-20261101-183750`), or all sessions. |
| **Event types** | Keep only some types, for example `perception.voice` and `perception.face`. |
| **Rows** | How many of the newest events to load (500 by default). |

The chart counts the selected events per type. The table shows each event: id, time, session,
type, reminder, bystander, the state it moved from and to, and its data as JSON, for example
`{"identity": "owner", "similarity": 0.4572, "plugin": "speechbrain_ecapa"}`.

## Download

**Download CSV** and **Download JSON Lines** export the selected events for analysis in pandas, R
or a spreadsheet. The [event log page](/research/event-log) lists every event type and what its
data holds.

## Pipeline feedback

Below the events, rate any reminder's run: whether it worked as it should, and with a thumbs down
what went wrong. **Run** lists the logged runs, newest first, and opens on the newest one not
rated yet, each with its reminder number, start time, how it ended (spoken, sent to the watch,
failed, unfinished) and whether it is rated. Above the thumbs, the models, thresholds and privacy
choices the run used. Rating a run again replaces the earlier verdict.

The table lists every rated run with its condition as columns; **Download feedback CSV** exports
it. The comments are kept with the feedback, never in the event log. See
[Pipeline feedback](/research/event-log#pipeline-feedback) for an analysis by model.

:::tip Scores for the thesis
`perception.voice` and `perception.face` carry the similarity to the owner and the plugin that
computed it; `flow.state` carries the reason for each step; `reminder.delivered` carries the
channel and how late it was. Filter by session to compare study conditions.
:::
