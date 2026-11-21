# 0002 , Store embeddings, never audio or images

**Status:** accepted (M0)

**Context.** Recognising the owner and remembering bystanders needs some stored representation
of faces and voices. Recordings would be the most sensitive data the system could hold.

**Decision.** Frames and audio exist only in memory. Only embeddings (float32 vectors tagged
with the model that produced them) and metadata are persisted. Bystander embeddings are stored
only together with an owner decision under the ask-once policy.

**Consequences.**
- Re-enrolment is needed after changing a face or speaker model, because embeddings are not
  comparable across models. The system refuses cross-model matches and fails closed.
- Experiments cannot be replayed from stored media. Use a researcher-supplied WAV file /
  image folder behind the `Microphone` / `Camera` protocols instead (read-only, never written by
  the robot; see ADR 0005).
- Enforced by a lint rule, by tests over the database contents, and by `.gitignore` and
  pre-commit size limits.
