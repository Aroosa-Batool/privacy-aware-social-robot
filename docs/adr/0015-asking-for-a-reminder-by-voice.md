# 0015 , Asking for a reminder by voice: only what is missing, at most three times

**Status:** accepted

**Context.** Set by voice, a reminder without a date got *On what date should I remind you?*,
even when it named a time ("at 3 pm"); one without a time silently became midnight
(`reminder.default_time`). Nothing heard, or nothing understood, ended the capture at once with
*Sorry, I didn't hear anything.* And an answer ended at the first 0.3 s pause
(`vad.min_silence_ms`, tuned for detecting voices, not for dictation), so "remind me to … call
the dentist … on Friday" was cut after its first words.

**What the research says.**
- *Which repair works.* Bohus and Rudnicky (2005) compared ten ways a spoken dialogue system
  can recover when it did not understand (46 users of a room-booking system). Asking to repeat
  ("Can you please repeat that?") recovered 34%, no better than staying silent (31%).
  Repeating the question recovered 49%; a short apology with an example of what to say
  ("Sorry, I didn't catch that. You can say …") 57%; moving on with a different, simpler
  question 64%. After one error the next turn is more likely to fail too, so each retry should
  make answering easier rather than ask for the same again.
- *How often to retry.* Google's conversation design guidelines give a first, rapid reprompt
  (a brief apology and the question, condensed) and a second with escalating detail (options or
  examples), and no more than three errors in a row before ending gracefully, telling the user
  another way to finish. On no input, assume the user did not hear the question: ask it again
  rather than "I didn't hear you". Dialogflow CX also caps no-match and no-input at three.
- *Apologising.* A robot that apologises for a breakdown keeps more of people's satisfaction
  than one that does not (Lee et al., HRI 2010).
- *Ending an answer.* With a fixed 500 ms end-of-speech pause, 36% of complex requests to a
  personal assistant were cut off (Arsikere, Shriberg and Ozertem, ICASSP 2014): speakers pause
  mid-request while they think. Raux and Eskenazi (2008) show that the right pause depends on
  where in the dialogue the system is.

**Decisions.**
- A time without a date is **today, or tomorrow once that minute has passed** ("at 15:00" said at
  15:01 is tomorrow; at 15:00:30 it is now). This holds however the reminder is added.
- By voice, the robot asks **only for what is missing**: with neither a date nor a time,
  *When should I remind you?*; with a date only, *At what time should I remind you?* (also after
  a "when?" answered with a date only). It never falls back to a default time.
- Each question is asked **at most three times**. Nothing heard within 15 s and an answer it
  cannot use are both a miss. The second time: *Sorry, I didn't catch that.* and the question.
  The third: *Sorry, I still didn't catch that.*, the question, and an example (*You can say, for
  example, tomorrow at 3 PM*). After the third miss: *Sorry, the reminder is not saved. Please try
  again, or type it on the dashboard.* The owner asked for "Sorry, can you say that again?";
  the research above is why the robot repeats the question and then gives an example instead.
- An answer ends after a **1 s pause** (`END_OF_TURN_MS`), not 0.3 s; listening for bystanders
  keeps `vad.min_silence_ms`.
- A date and time named outright that have already passed ("today at 8 am" at 9 am) are not
  saved: *Sorry, that time has already passed …*

**Consequences.**
- A capture can now take up to about four minutes (three questions, three tries each); the
  dashboard waits that long.
- The robot waits a second after each answer before it replies.
- Typed reminders (dashboard, terminal) still ask for a missing date and use
  `reminder.default_time` for a missing time, which the dashboard shows before saving.
- Not adopted: moving on to a simpler question (the best strategy in Bohus and Rudnicky) beyond
  splitting "when?" into date and time, and confirming explicitly after errors; both would add
  turns, and the spoken confirmation already says the date and time.
- Inferences, not measured on this robot: the 1 s pause, the 15 s wait, and the examples.

**Sources.**
- D. Bohus, A. Rudnicky, "Sorry, I Didn't Catch That! An Investigation of Non-understanding
  Errors and Recovery Strategies", SIGdial 2005: <https://aclanthology.org/2005.sigdial-1.14>
- Google, conversation design, errors (no match, no input):
  <https://developers.google.com/assistant/conversation-design/errors>
- Google Cloud, Dialogflow CX voice agent design:
  <https://cloud.google.com/dialogflow/cx/docs/concept/voice-agent-design>
- M. K. Lee, S. Kiesler, J. Forlizzi, S. Srinivasa, P. Rybski, "Gracefully Mitigating Breakdowns
  in Robotic Services", HRI 2010:
  <https://www.ri.cmu.edu/publications/gracefully-mitigating-breakdowns-in-robotic-services>
- H. Arsikere, E. Shriberg, U. Ozertem, "Computationally-Efficient Endpointing Features for
  Natural Spoken Interaction with Personal-Assistant Systems", ICASSP 2014:
  <https://www.sri.com/publication/information-computer-science-pubs/computationally-efficient-endpointing-features-for-natural-spoken-interaction-with-personal-assistant-systems/>
- A. Raux, M. Eskenazi, "Optimizing Endpointing Thresholds using Dialogue Features in a Spoken
  Dialogue System", SIGdial 2008: <https://aclanthology.org/W08-0101>
