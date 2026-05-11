# 🤖 Automation Stage Generator (`autostages`)

`autostages` is a **stage-driven automation framework** for building and running iterative LLM workflows.

---

## ✨ Features

- 🧩 **Define stage specs in Markdown** (`.autostages/stages/*.md`)
- 🛠️ **Auto-generate Python stage scripts** (`.autostages/src/stages/*.py`)
- 🔁 **Run loop-capable stage flows** (based on `evaluate_end_condition`)
- 🕸️ **Generate and validate stage graphs** (DAG check for normal edges)
- 🚀 **Multiple generation backends**
  - Codex CLI
  - Claude CLI
  - OpenAI API
  - Google API (Gemini)
  - Claude API
- 🖥️ **Local / SLURM execution support**
- 💾 **Persist session/config/run artifacts** (`.autostages/cache`, `.autostages/config.json`)

---

## 📦 Requirements

- 🐍 Python `3.11`
- 🔑 API keys for the backends you use
  - `OPENAI_API_KEY`
  - `GEMINI_API_KEY`
  - `ANTHROPIC_API_KEY`
- (Optional) CLIs for CLI-based generation
  - `codex`
  - `claude`

---

## 🏁 Setup

### 1. Clone

```bash
git clone <this-repo-url>
cd 05_autoresearch
```

### 2. Install dependencies

Using `pixi`:

```bash
pixi install
```

Using minimal `pip` setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install openai google-generativeai rich
```

### 3. Install package

```bash
pip install -e .
```

This installs the `autostages` command.

### 4. Export API keys

```bash
export OPENAI_API_KEY=...
export GEMINI_API_KEY=...
export ANTHROPIC_API_KEY=...
```

---

## ▶️ Run

```bash
autostages
```

Startup menu:

1. `Run stage flow`
2. `Generate Python scripts from stage markdown`
3. `Check graph.json`

Pin provider/model explicitly:

```bash
autostages --provider openai --model o4-mini-2025-04-16
autostages --provider codex --model gpt-5.4
autostages --provider claude --model claude-sonnet-4-20250514
```

---

## 🗂️ Runtime Layout

The CLI creates and uses `.autostages/` in your current workspace:

```text
.autostages/
├── cache/
│   ├── session.json
│   └── run_*.json
├── config.json
├── graph.json
├── stages/
│   └── *.md
└── src/
    └── stages/
        └── *.py
```

- 🧭 `graph.json` is generated from stage markdown `Header` values
- 🧪 Run history is stored as `cache/run_<timestamp>_<id>.json`
- 🧱 Generated stage scripts are saved under `src/stages/`

---

## 🧾 Stage Markdown Contract

Each stage markdown should include a `## Header` section with keys like:

- `Stage Name`
- `Stage Id`
- `Previous Stage`
- `On Success`
- `On Incomplete`
- `Start Condition`
- `End Condition`

These values are used to build graph edges.

---

## 🧠 Stage Script Requirements

Every generated/manual stage script must:

- define one `AbsStage` subclass
- implement `run_body(self, provider, messages)`
- implement `evaluate_end_condition(self, runtime_dirs, messages)`

If `evaluate_end_condition` is not overridden, flow execution fails at that stage.

---

## ⚙️ Orchestration

Execution behavior is controlled by `.autostages/config.json`:

- `orchestration.executor_type`: `local` / `slurm`
- `orchestration.poll_interval_sec`
- `orchestration.max_stage_steps`
- `orchestration.slurm`: `partition`, `cpus_per_task`, `mem`, `time`

- 🏠 `local`: runs worker subprocesses directly
- 🛰️ `slurm`: submits with `sbatch`, polls with `sacct`

---

## 🧱 Repository Structure

```text
autostages/
├── cli.py
├── resources/
│   ├── system_prompt.md
│   ├── stages/
│   └── stage_references/
└── src/
    ├── analyze_dir.py
    ├── orchestration/
    ├── providers/
    └── stages/
```

---

## 🔄 Migration Note

Legacy `dataset wizard` documentation is obsolete.  
This codebase now focuses on **general stage automation workflows**, not dataset-specific scaffolding.

---

## 📜 License

MIT
