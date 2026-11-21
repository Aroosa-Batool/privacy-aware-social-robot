# 0001 , Streamlit for the researcher dashboard

**Status:** accepted (M0)

**Context.** Researchers need to see the pipeline, run it, swap algorithms and tune many
parameters without being overwhelmed. The project has one developer, and the robot code is all
Python.

**Decision.** Use Streamlit, running the robot in-process on a background thread
(`RuntimeHandle`). Settings forms are generated from the pydantic schema; the algorithms page
groups the stages by Microphone, Camera and Sensitivity. Pages are grouped in the sidebar
(Robot / Owner / Configure).

**Consequences.**
- No second language, build step or HTTP API to maintain. New plugins and their parameters
  appear in the UI automatically; a new stage setting is listed once in the algorithms page.
- Streamlit re-runs scripts on every interaction, so the runtime must live outside script runs
  (`st.cache_resource`), and live views poll (`st.fragment(run_every=1s)`) rather than receive
  pushed events.
- If a multi-user or mobile UI is ever needed, put an HTTP API in front of `Runtime`. The core
  does not depend on Streamlit.
