# InsightOS

**Future Core AI Analytics Engine** - AI-assisted, evidence-driven, end-to-end data
preprocessing and consistency improvement. Primary language: Python **3.11**.

> **Authoritative architecture document: [`INSIGHTOS_PROJECT_BLUEPRINT_V2.md`](INSIGHTOS_PROJECT_BLUEPRINT_V2.md).**
> If this README and Blueprint V2 disagree, Blueprint V2 wins. Unresolved specifications are
> listed in its section 16 (Open Items).

## Status

**Phase 1 - Project Foundation only.** Implemented: packaging, centralized configuration, the
versioned Pydantic schema base, the run/artifact store, secret-redacting logging, an
`evaluation/` scaffold, and a minimal CLI. **Not implemented:** ingestion, profiling, DCQS,
detection, LLM reasoning, cleaning, validation, reporting. This repository was reconstructed
after the original was lost; no later-phase code exists.

## Core principle

Python executes and measures; the LLM only reasons and recommends. The LLM must not modify raw
data, calculate the score, invent missing values, or emit code. There is no automatic
missing-value imputation in V1, and review-required actions are never auto-executed.

```
Ingestion -> Profiling -> Detection -> Initial DCQS -> LLM Reasoning -> CleaningPlan
          -> Risk/Review Gate -> Cleaning -> Independent Validation -> Final DCQS -> Reporting
```

## Layout

```
src/insightos/
  settings.py        centralized configuration (pydantic-settings)
  schemas/           InsightOSModel (strict, frozen) and VersionedArtifact (schema_version)
  runs/              run directories, immutable input, atomic artifact persistence
  logging_setup.py   logging with secret redaction
  errors.py          exception hierarchy
  cli.py             `insightos info` / `--version`
evaluation/          evaluation harness scaffold (repo-level, not shipped in the wheel)
config/default.toml  non-secret defaults
tests/               Phase 1 tests
```

Run artifacts live in `runs/<run_id>/` (git-ignored): `manifest.json` plus `input/` (read-only
original, SHA-256 recorded), `profile/`, `detection/`, `scoring/`, `llm/`, `cleaning/`,
`validation/`, `report/`.

## Configuration

Precedence (highest first): init kwargs > environment (`INSIGHTOS_*`) > `.env` > TOML file
(`INSIGHTOS_CONFIG_FILE`, else `config/default.toml`) > built-in defaults. Secrets (the LLM API
key) are `SecretStr`, never go in TOML or the repository, and are masked in `insightos info` and
in logs. Copy `.env.example` to `.env` (git-ignored) to set them.

## Development

```
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
mypy
insightos info
```

## Security

Never commit `.env`, API keys, or run artifacts. `.gitignore` excludes them.
