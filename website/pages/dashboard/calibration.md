---
title: Calibration
description: Measure how alike the robot finds the owner and other people, see the two groups on one scale, and choose the threshold between them.
---

The **Calibration** page (Settings › Calibration) explains what a threshold is, then measures it
with the robot running, so the robot does not have to be stopped as for
[`pasr calibrate`](/research/calibration). It opens with two short guides, **What is
calibration?** and **How to do it**, folded away once you have measured yourself.

:::steps
@step Choose face or voice

The current threshold and the model's recommended starting point are shown. The owner must be
enrolled first (on [Profile](/dashboard/profile)).

@step Measure yourself

Sit alone in front of the robot and click **Measure me**. For the face, the robot asks for the
same poses as enrolment (about half a minute, 20 samples); for the voice, talk for about half a
minute until 6 stretches of speech are in.

@step Measure other people

One or two other people, **one at a time, alone in view**: frames with two faces are not used.
Each clicks **Measure another person** and follows the same instructions. Their samples are
scored and forgotten; tell them it is for your research.

@step Choose the line and save it

A chart puts every sample on the similarity scale, yours in blue and the others' in orange, with
the threshold as a line. The slider starts at the suggested line; moving it shows how many of
your samples and of the others' would count as you. A badge says how well the groups separate
(good, fair, poor). **Save** stores the threshold and the running robot uses it at once.
:::

Measured alone, the suggestion never goes above the model's recommended starting point: your
own samples show how low the line may go, not how high. Nothing but the threshold is stored,
and each save is logged as `identity.calibrated`. The maths is described under
[Calibrate thresholds](/research/calibration).
