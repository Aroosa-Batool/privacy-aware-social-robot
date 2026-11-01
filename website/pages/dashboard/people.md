---
title: People and consent
nav: People & consent
description: Who the robot knows: the owner's enrolment, the anonymous bystanders it remembers, and every consent answer, with ways to forget them.
---

Bystanders are remembered only if the owner chose to remember watch answers (on
[Profile](/dashboard/profile)), and only together with an answer: as an anonymous label and an
embedding, never a picture or a recording.

::image src=/assets/media/people.webp alt="The People & consent page: the owner with 5 face and 3 voice samples, and a table of bystanders B-001 to B-009 recognised by face." url=localhost:8501/people caption="Bystanders are labels like B-001; the robot never knows their names."

## Owner

The owner's name, when they registered, and one row per biometric: the number of samples and the
model that produced them.

## Bystanders

| Column | Meaning |
|---|---|
| label | An anonymous label, `B-001`, `B-002`, … |
| recognised by | `face` or `voice`, whichever first identified the person. |
| first seen · last seen | When the robot first and last matched them. |
| times seen | How often they were recognised again. |
| may hear sensitive reminders | The owner's remembered answer: yes or no. |

Each bystander keeps at most five embeddings. **Forget a bystander** deletes the person, their
embeddings and their consent answers in one go.

## Consent history

Every remembered answer with its time and source. **Delete last consent** withdraws the most
recent active answer, so the robot asks about that person again. From a terminal:

```bash
uv run pasr consent list
uv run pasr consent delete-last          # revoke: kept, marked revoked, for the audit trail
uv run pasr consent delete-last --hard   # delete the record outright
```

:::privacy Deleting really deletes
SQLite's `secure_delete` overwrites deleted rows, and forgetting a bystander cascades to their
embeddings and answers. To delete every bystander at once, use [Reset](/dashboard/reset).
:::
