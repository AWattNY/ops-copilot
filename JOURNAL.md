# Journal

A running log of the 14 days. Fill in Environment before Day 1, then add one entry per
day (about 30 minutes at the end of the day). Raw and honest beats polished: failures
written down here become eval cases, `DECISIONS.md` updates, and interview examples.

---

## Environment (fill in before Day 1)

| Item | Value |
|---|---|
| Mac / chip / memory | 64 GB |
| Python version (`python3 --version`) | Python 3.14.7 |
| Ollama version (`ollama --version`) | 0.35.1 |
| LangChain version (`pip show langchain`) | 1.4.3 |
| Fork URL | https://github.com/AWattNY/full-stack-fastapi-template |
| Pinned fork commit (`git rev-parse HEAD`) | 1762adac607a1b29cfc4da129557780beea71616 (branch agent-playground) |
| `AGENT_WORKSPACE` | /Users/awatt/code/fastapi-app/backend |
| `AGENT_NUM_CTX` | 65536 |
| `ollama ps` shows: 65536 / 100% GPU (12 GB)
| Main model (after the Day 1 bake-off, see `DECISIONS.md` D5) | |
| Hosted model + spend cap | |
| `python -m unittest` result: 17 passed ✅
| First real tool call (`-> list_dir` seen?) Yes: list_dir({'path': ''}), output matched ls -a
| `requirements.lock` committed? | Yes |

---

## Day template (copy for each day)

### Day N: <title> (date)

**Must status:** done / partial / not done, and which items slipped

**What worked:**

**What broke** (paste the symptom, then what the cause turned out to be):

**What surprised me:**

**New eval cases from today's failures:**

**Decisions made or changed** (add to `DECISIONS.md` if you'd defend it in an interview):

**Tomorrow's first step:**

---
## Setup notes (before Day 1)

### Same model, no harness: `ollama run` vs. the agent loop

**What I ran:** `ollama run gpt-oss:20b 'List the files in the workspace root'`

**What happened:** the model said it has no filesystem access and offered a generic list
of files a project "might" have (`.git`, `src/`, `README.md`, ...). Its visible thinking
considered simulating an answer, then chose to say it couldn't access the files.

**Why:** `ollama run` is a plain chat. There are no tools and no workspace, so the model
has no way to look. A model alone can only answer from memory; the harness (the loop
plus tools) is what lets it act.

**Good sign for the bake-off:** gpt-oss admitted it couldn't see the files rather than
inventing a confident answer. The opposite, describing files it never opened, is one of
the failure modes I'm scoring.

**To compare:** run the same question through `phase0_raw_loop.py`. Expect a
`-> list_dir(...)` line and the real file list. Paste both outputs side by side here.

### Misunderstanding: what `AGENT_NUM_CTX` affects

**What happened:** I set `AGENT_NUM_CTX=65536`, used `ollama run`, then `ollama ps`
showed nothing.

**What I learned:**
- `AGENT_NUM_CTX` is read only by my scripts. `ollama run` used Ollama's default, which on
  this Mac was the model's maximum: `ollama ps` showed CONTEXT 131072, 100% GPU, 13 GB.
- `ollama ps` reports the one Ollama server, so it's the same in any terminal. It was empty
  earlier because no model was loaded at that moment (models unload after ~5 min idle).
- Lesson: on 64 GB, the default context isn't the risk; reproducibility is. Set it
  explicitly so every eval run uses the same, recorded value.

**Eval case idea:** "When the tools can't reach something, does the agent say so instead
of guessing?" Possible `recovery` case: point it at a path outside the workspace and
check that it reports the error instead of inventing contents.

### Port conflict on `docker compose up`

**What I ran:** `docker compose up` in `~/code/fastapi-app`

**What happened:** images pulled and built, Postgres became healthy, and the backend
started. Then `adminer` failed: "Bind for 0.0.0.0:8080 failed: port is already allocated".

**Why:** my existing Open WebUI container was already using port 8080.

**Fix:** `docker stop open-webui`, then `docker compose up` again.

**What I learned:**
- Read past the noise to the last error line. Most of the output (Traefik `DBG`/`WRN`
  lines) was normal logging, not failures.
- "pull access denied for backend" is harmless: Compose tries Docker Hub first, then
  builds the image locally (`Image backend:latest Built`).
- If I need Open WebUI and the template at the same time:
  `docker compose up -d --scale adminer=0`. Adminer isn't used by the curriculum.
- Use `docker compose up -d` to get the prompt back, and `docker compose logs backend`
  to see one service's logs.

## Day 1: Phase 0, the minimal harness ()
