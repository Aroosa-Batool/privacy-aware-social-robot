---
title: Reset
description: Delete what the robot has learned about other people and your preferences, and optionally the owner too. A reset cannot be undone.
---

A reset **always** deletes:

- every remembered bystander and their embeddings,
- every remembered consent answer,
- your preferences (every setting returns to its default).

You choose whether the **owner** is deleted too: name, face and voice embeddings, and reminders.
The research event log holds no personal content and is kept unless you tick
*Also delete the research event log*. Tick *I understand this cannot be undone* and click
**Reset**; the robot is stopped first.

| | Bystanders and embeddings | Consent answers | Preferences | Owner name, face, voice | Reminders | Event log |
|---|---|---|---|---|---|---|
| Reset, keep owner | deleted | deleted | deleted | kept | kept | kept |
| Reset, delete owner | deleted | deleted | deleted | deleted | deleted | kept |
| with *delete the event log* | | | | | | deleted |

From a terminal:

```bash
uv run pasr reset --keep-owner             # asks for confirmation
uv run pasr reset --delete-owner --purge-log --yes
```

:::danger It really deletes
SQLite's `secure_delete` overwrites the deleted rows, and the reset checkpoints the write-ahead
log, so nothing lingers in the database file. Export the [event log](/dashboard/events) first if
you still need it.
:::

To take back a single answer instead, use **Delete last consent** or **Forget a bystander** on
[People & consent](/dashboard/people).
