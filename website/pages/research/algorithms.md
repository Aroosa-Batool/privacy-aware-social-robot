---
title: Swap algorithms
description: Every stage of perception is a plugin behind a protocol. Choose one per stage on the dashboard or in settings, tune its parameters, or register your own.
---

## The stages

| Stage | Setting | Plugins |
|---|---|---|
| Face detection and embedding | `perception.face` | `insightface` |
| Speaker embedding | `perception.speaker` | `speechbrain_ecapa`, `resemblyzer` |
| Voice activity | `perception.vad` | `silero`, `energy` |
| Speech-to-text | `perception.stt` | `faster_whisper` |
| Sensitivity | `perception.sensitivity` | `zero_shot`, `keyword` |
| Date and time | `perception.datetime_parser` | `dateparser` |

Choose them on [Models](/dashboard/models), or:

```bash
uv run pasr config set perception.vad.plugin energy
uv run pasr config set perception.sensitivity.params.threshold 0.6
uv run pasr config show --level advanced      # every plugin parameter
```

Each plugin declares its parameters as a pydantic model, tagged *basic* or *advanced*; the
dashboard renders a form for them automatically.

## Add your own

:::steps
@step Implement the protocol

Write a class implementing one protocol from `perception/protocols.py`, with a nested pydantic
`Params` model. Declare each field with `pasr.settings.tiers.setting(default, tier=...,
description=...)`. Load heavy models lazily, on first use.

```python
from pydantic import BaseModel
from pasr.settings.tiers import setting


class MyVAD:
    class Params(BaseModel):
        threshold: float = setting(
            0.5, tier="basic", ge=0, le=1, description="Speech probability that counts as speech."
        )

    def __init__(self, params: "MyVAD.Params") -> None:
        self.params = params

    ...
```

@step Register it

Add a `PluginSpec` to `perception/registry.py`, or call `registry.register(...)` from your own
package. A spec names the kind, the plugin name, a one-line description, the import target
(`"package.module:Class"`) and the Python modules it needs.

@step Choose it

It appears on the dashboard's Models page with its parameters, and can be chosen per stage in
settings. A face or speaker plugin can declare `recommended_threshold` as a starting point for
calibration.
:::

:::warning Embeddings carry their model
Every stored embedding records the model that made it, and matching against another model raises
(and fails closed). After switching the face or speaker plugin, enrol the owner again and
[re-calibrate](/research/calibration).
:::

More on the plugin system in [Extending PASR](/reference/extending).
