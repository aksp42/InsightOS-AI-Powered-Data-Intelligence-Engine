# InsightOS — Project Blueprint V2

**Status:** Authoritative architecture document. Supersedes `INSIGHTOS_PROJECT_BLUEPRINT.md` (V1).
**Sources merged:** Blueprint V1, the DCQS scoring specification, and the architecture decisions
agreed during the Phase 0 review and the Phase 1 approval.

Conventions used in this document:

- **Decided** = agreed and binding.
- **OPEN** = deliberately unresolved. No formula, threshold or design is final until it is
  resolved and recorded here. Open items are collected in [section 16](#16-open-items).
- Illustrative numbers (scores, percentages) are examples only. **No score, weight, threshold or
  model in this document is validated.**

---

## 1. Project Identity

- **Project:** InsightOS
- **Tagline:** Future Core AI Analytics Engine
- **Primary language:** Python (**3.11**)
- **Goal:** AI-assisted, evidence-driven, end-to-end data preprocessing and consistency
  improvement.

## 2. Core Problem

Real-world datasets contain missing values, duplicates, inconsistent types and formats,
categorical and unit inconsistencies, invalid values, anomalies, and schema issues. Manual
preprocessing is time-consuming, error-prone, and difficult to reproduce.

## 3. Core Solution

The user uploads messy CSV/Excel data. InsightOS profiles it, detects issues, calculates an initial
Data Consistency & Quality Score (DCQS), uses an LLM for semantic reasoning and cleaning
recommendations, executes only approved transformations through Python, independently validates
the result, recalculates the score, and produces a clean dataset plus an explainable quality
report.

## 4. Core Principles

| Role | Owner |
|---|---|
| Reasoning / recommendation | LLM |
| Execution | Python cleaning engine |
| Evidence | Detection |
| Measurement | DCQS scoring (deterministic) |
| Quality inspection | Independent validation |

**Binding rules**

1. Python executes. Deterministic engines measure. The LLM only reasons and recommends.
2. The LLM must not directly modify raw data, calculate the score, invent missing information,
   emit code, or make unsupported destructive changes.
3. The original data is immutable. Cleaning always works on a copy.
4. **No automatic missing-value imputation in V1.** Missing values are not invented or inferred.
   They remain unresolved and are reported, unless a future, explicitly approved imputation
   feature is added. Imputation actions (e.g. median/mode) are **not** part of the V1
   CleaningPlan vocabulary.
5. UserRules are optional. Inferred rules and user-provided rules must always be clearly
   distinguished.
6. Review-required actions are never auto-executed, including in non-interactive mode. They remain
   unchanged and are reported as unresolved / review-required items.
7. Similarity never implies semantic equivalence. Outliers are flags, not automatic errors.
8. A high DCQS never means validation passed.
9. Every run is reproducible from persisted artifacts (see section 12).
10. The LLM provider is pluggable. Secrets never enter the repository.

## 5. End-to-End Flow (Decided)

```
Ingestion → Profiling → Detection → Initial DCQS → LLM Reasoning → CleaningPlan
          → Risk/Review Gate → Cleaning → Independent Validation → Final DCQS → Reporting
```

Compared with V1, Detection now precedes scoring: detectors produce the evidence and DCQS
aggregates it, so the same measurements are never computed twice. A Risk/Review Gate sits
explicitly between the CleaningPlan and Cleaning.

### Data flow / interfaces

```
Raw File → IngestionResult → DatasetProfile → DetectedIssues → ConsistencyScore (initial)
         → LLMAnalysisRequest → LLMReasoningResult → CleaningPlan → (Risk/Review Gate)
         → CleanedDataset + ChangeLog → ValidationResult → FinalConsistencyScore → QualityReport
```

Modules communicate through typed, structured objects (Pydantic models), not by sharing and
mutating DataFrames. How the dataset itself is handed between modules (for example a thin
dataset handle that keeps the Pandas/Polars choice reversible) is OPEN (section 16).

## 6. Component Boundaries

| Component | Answers | Must not |
|---|---|---|
| Ingestion | How is the original loaded and preserved? | Interpret or clean |
| Profiler | What is the current state? | Modify data; decide what is wrong |
| Detection | What appears wrong? | Fix anything; treat similarity as equivalence |
| DCQS scoring | How consistent / good is it? | Use LLM opinion |
| LLM reasoning | What does it mean and what should be done? | Touch raw data, score, impute, emit code |
| CleaningPlan | What exactly may be executed? | Accept unknown actions or parameters |
| Risk/Review gate | Which steps may run? | Auto-execute review-required steps |
| Cleaning engine | Apply approved steps to a copy | Mutate the original |
| Validation | Was the transformation safe and valid? | Treat a high score as a pass |
| Reporting | Explain the result | Hide missing values or unresolved issues |

## 7. Modules

### 7.1 Data Ingestion

- **Formats (V1 scope):** CSV, and Excel with **one selected sheet**. Multi-sheet processing is
  future scope. Future formats: JSON, Parquet, database sources.
- **Responsibilities:** accept supported files, validate basic input, preserve the original data
  immutably, and produce an `IngestionResult` containing the dataset and metadata.
- **No silent inference:** ingestion must not silently convert null-like tokens or guess types, so
  that profiling and detection see the data as it actually is. The detailed ingestion contract
  (encodings, delimiters, header-row handling, merged cells, etc.) is OPEN.
- **File/row limits:** to be finalized during implementation and performance testing (OPEN).
- **Original preservation:** the uploaded file is stored byte-for-byte as a read-only input
  artifact with its SHA-256 recorded (section 12).

### 7.2 Data Profiler

Purpose: describe the current dataset **without modifying it**.

- **Dataset level:** row/column count, file type/size, missing cells, duplicate rows, empty
  rows/columns, memory usage.
- **Column level:** numerical statistics, categorical frequencies/cardinality, text
  length/whitespace/case patterns, date formats/validity, storage type vs potential semantic type,
  relevant patterns.
- **Null tokens:** potential null tokens are flagged intelligently. Values such as "Unknown" are
  **not** automatically treated as missing.
- **Output:** structured `DatasetProfile`.

### 7.3 Issue Detection Engine

Initial categories:

1. Missing values
2. Exact duplicates
3. Near duplicates
4. Data-type inconsistencies
5. Format inconsistencies
6. Categorical/text inconsistencies
7. Unit/numerical inconsistencies
8. Invalid values
9. Anomalies/outliers
10. Schema issues

Rules:

- Detection is separate from cleaning and produces the evidence DCQS consumes.
- Each issue carries: `issue_id`, `issue_type`, `column`, affected rows/count, percentage,
  severity, evidence, detection method, status.
- Every rule or expectation applied is labelled **inferred** or **user-provided**.
- Similarity alone must not imply semantic equivalence. Outliers are flags, not automatic errors.
- Near-duplicate and category-similarity detection methods are OPEN (section 16).

### 7.4 Data Consistency & Quality Scoring Engine (DCQS)

See [section 8](#8-dcqs-specification) for the full specification.

### 7.5 LLM Reasoning Engine

**Responsibilities:** semantic schema/column understanding, semantic inconsistency
interpretation, candidate mappings, cleaning recommendations, ambiguity detection, explanations,
and structured recommendations that feed the CleaningPlan.

**Input:** structured profile/issue evidence and a minimum set of representative samples. Never
the complete dataset by default.

**Output:** schema-validated JSON containing fields such as `issue_type`, `column`,
`recommended_action`, `mapping/parameters`, `confidence`, `reason`, `human_review_required`.

**Privacy and safety (Decided)**

- Send only the minimum required evidence/samples to an external LLM.
- Support masking/redaction of sensitive values.
- Never send the complete dataset by default.
- Treat uploaded cell values as **untrusted data** (they can contain instructions). Output is
  strictly validated against the schema regardless of what the model returns.

**Provider:** pluggable. **Gemini API is only the initial candidate**; it is not locked. Qwen or
other suitable models may be added, and the final selection will be benchmarked using the
evaluation harness. API keys live only in environment variables / secrets and are never
committed.

The LLM does not impute missing values, compute scores, or emit executable code.

### 7.6 CleaningPlan, Risk/Review Gate, and Cleaning Engine

**Principle:** the LLM recommends; Python executes.

**CleaningPlan (Decided):** a structured, **typed, closed-vocabulary** plan. Only whitelisted
action types with typed parameters are accepted; unknown actions or parameters are rejected.
Mappings proposed by the LLM must be verified against values that actually exist in the data.
Imputation actions are not in the V1 vocabulary. The exact action list, execution ordering, and
idempotence rules are OPEN (section 16).

**Risk/Review Gate (Decided):** each plan step is routed by risk and confidence to one of:

- **Auto-apply (safe automatic):** whitespace trimming, clearly defined null normalization,
  unambiguous case/date/number normalization, approved exact duplicate removal, safe type
  conversion, clearly valid unit conversion.
- **AI-assisted:** semantic category standardization and context-dependent normalization.
- **Human review required:** ambiguous category merges, uncertain value correction,
  destructive/high-risk changes.

Review-required actions are **not executed**, even in non-interactive mode. The data stays
unchanged for those items and they are reported as unresolved / review-required. Confidence and
risk thresholds are OPEN.

**Cleaning Engine:**

- Applies only approved steps, on a copy of the data. The original is immutable.
- Every modification generates a `ChangeLog`.
- Unit conversion factors are deterministic (library/table), never supplied by the LLM.
- Currency conversion is out of V1.
- Validation failure must allow rejection/rollback.
- ChangeLog row identity and scale handling, and rollback granularity, are OPEN.

### 7.7 Independent Validation Engine

Purpose: verify cleaning safety and resulting data validity. Validation is independent of the
cleaning engine's internals and checks the result against the original data and the ChangeLog.

**Checks:** structural/schema integrity, data types, missing values, duplicates, formats,
categories, numerical ranges/conversions, unexpected modifications, excessive row deletion,
transformation impact, integrity constraints.

**Statuses:** `PASSED`, `PASSED_WITH_WARNINGS`, `FAILED`, `REVIEW_REQUIRED`.

A high DCQS does **not** automatically mean validation passed. Explicit status criteria and
thresholds (for example, acceptable row deletion) are OPEN.

### 7.8 Reporting

Outputs:

1. Clean dataset
2. Before/after DCQS
3. Issue detection report
4. Cleaning plan
5. Change log
6. Validation report
7. Unresolved issues (including all missing values that remain)
8. Human-review items

## 8. DCQS Specification

The scoring engine is officially named the **Data Consistency & Quality Score (DCQS)**, because it
measures consistency, completeness, validity, structural quality, and anomaly state — not
consistency alone. The UI may simply show "Data Quality Score: 61.3% → 96.8%" (illustrative);
internally it is DCQS.

### 8.1 Overall score

A 0–100 score, a weighted average over **applicable** dimensions only:

```
Score = Σ(Wᵢ × Sᵢ) / Σ(Wᵢ)
```

- `Sᵢ` = dimension score (0–100)
- `Wᵢ` = weight of an *applicable* dimension

If a dimension is not applicable to the dataset, its weight is removed from the denominator. For
example, with applicable weights summing to 85, the score is `weighted_sum / 85`, not `/ 100`.
A dataset with no date columns, no categorical columns, or no units is not punished.

### 8.2 Dimensions and initial weights

| Dimension | Initial weight |
|---|---:|
| Missing Value / Completeness | 15 |
| Duplicate Consistency | 15 |
| Data Type Consistency | 10 |
| Format Consistency | 15 |
| Categorical Consistency | 10 |
| Numerical / Unit Consistency | 10 |
| Value Validity | 10 |
| Schema Consistency | 10 |
| Anomaly Handling | 5 |
| **Total** | **100** |

**Weights are initial engineering assumptions and must be calibrated through the evaluation
harness.**

### 8.3 Dimension definitions

**Missing Value / Completeness (15)** — genuine missing values **are penalized**.

```
Completeness = 100 × (1 − MissingCells / EligibleCells)
```

Illustration: 10,000 eligible cells, 800 missing → 92.

Inconsistent null representations (e.g. `NULL`, `NaN`, `N/A`, `NA`, `-`, empty string,
`"unknown"`) are detected as a **separate issue**. `"Unknown"` is **not** automatically treated
as missing. The definition of "eligible cells" and the final null-token handling are OPEN.

*Imputation (superseding the DCQS draft):* the DCQS draft mentioned median/mode imputation for
numeric/categorical columns. That is **superseded**: V1 performs no automatic imputation (section
4, rule 4). Identifier-like fields are never invented.

**Duplicate Consistency (15)**

```
DuplicateScore = 100 × (1 − DuplicateRows / TotalRows)
```

Illustration: 10,000 rows, 500 duplicates → 95.

**Data Type Consistency (10)** — measured per column against its expected/inferred semantic type:

```
Valid typed values / Eligible values
```

Illustration: Age with 980 valid numeric and 20 invalid → 98. Mixed values such as `25`, `30`,
`"unknown"`, `"twenty"` lower the score. Dominant-type inference rules and thresholds are OPEN.

**Format Consistency (15)** — detects the same semantic value written in different formats
(dates such as `2026-01-10`, `01/10/2026`, `10-Jan-2026`; phone numbers such as `+91 9876543210`,
`9876543210`, `0919876543210`; email pattern validity).

```
FormatScore = 100 × ConsistentValues / EligibleValues
```

**Categorical Consistency (10)** — detects variants such as `Male`, `M`, `male`, `MALE`; the score
improves after standardization. Values such as `Delhi`, `Delhi NCR`, `New Delhi` are **not**
automatically considered the same: they require LLM recommendation, evidence, and review. The
formula is OPEN.

**Numerical / Unit Consistency (10)** — checks numeric consistency, unit consistency, scale
inconsistencies, and impossible conversions (e.g. `70 kg` and `70000 g` are consistent after
conversion). Conversion factors are deterministic, never invented by the LLM. Currency conversion
is out of V1. The formula is OPEN.

**Value Validity (10)** — checks values against:

- *Generic rules:* e.g. Age < 0 invalid; Percentage > 100 invalid; Quantity < 0 invalid where the
  domain requires non-negative.
- *UserRules, when provided:* e.g. `age: 18–100` makes `25` valid and `120` invalid.
- *Without UserRules:* only conservative statistical/pattern-based checks, and the system must not
  claim business correctness.

The formula is OPEN.

**Schema Consistency (10)**

- *With UserRules:* validate against explicit expectations (e.g. `customer_id` unique, `age`
  integer, `gender` categorical).
- *Without UserRules:* only structural/inferred checks — duplicate column names, empty headers,
  unnamed columns, inconsistent inferred types, suspicious header rows, schema irregularities.
  The system cannot claim business-schema correctness without a reference schema.

The formula is OPEN.

**Anomaly Handling (5)** — outlier ≠ error. The score is not simply "outlier found = bad":

- No anomaly detected → 100
- Anomalies detected → lower
- Anomaly reviewed / appropriately handled → improvement

V1 baseline: **IQR / robust statistical methods**. Isolation Forest remains a candidate for later
comparison. The meaning of "handled" for an anomaly that is deliberately not changed, and the
formula, are OPEN.

### 8.4 Baseline and anti-gaming

Scoring must not be gameable by deleting or nulling bad data.

- The **original dataset is the baseline**. Final metrics are evaluated against the original
  baseline and transformation impact, not against the cleaned dataset's smaller size alone.
- If cleaning removes rows (e.g. 10,000 → 8,000 by deleting 2,000 problematic rows), the score
  must **not** become 100.
- Flow: Original Dataset → Baseline Metrics → Cleaning → Final Metrics → Impact Penalty → Final
  Score.
- The exact **impact-penalty coefficient is to be calibrated experimentally** in the evaluation
  phase, not chosen arbitrarily now.
- Further gaming vectors beyond row deletion (nulling invalid cells, over-merging categories, lossy
  type coercion), and how legitimate approved exact-duplicate removal is treated, are OPEN.

### 8.5 Before vs after

Before and after scores are computed with **the same scoring specification**.

```
Improvement = After − Before   (in percentage points)
```

Illustration only: 61.3 → 96.8 is +35.5 percentage points. These numbers are not validated and
may not be reachable under the V1 no-imputation rule.

Inconsistency percentage is defined as `100 − score`.

### 8.6 Locked scoring decisions

- 0–100 score with weighted dimensions
- N/A dimensions excluded from the denominator
- Genuine missing values are penalized; inconsistent null representation is detected separately
- The original dataset is the baseline
- Row deletion cannot automatically produce a perfect score
- Outliers are not automatically errors
- The LLM does not calculate the score
- Before/after use the same specification
- UserRules are optional
- The anti-gaming penalty coefficient is determined in the evaluation phase

## 9. UserRules (Optional, Decided)

UserRules are an optional input (for example expected types, allowed ranges, unique keys, domain
value lists). They feed Value Validity and Schema Consistency. Without UserRules, InsightOS relies
on inferred rules only, and every rule in a report is labelled **inferred** or **user-provided**.
The UserRules format is OPEN.

## 10. Technology Strategy

- **Primary language:** Python **3.11** (decided).
- **Structured contracts:** Pydantic models; persisted artifacts carry `schema_version` (decided).
- **Configuration:** centralized application configuration; non-secret settings in config,
  secrets/API keys via environment variables / `.env`; `.env.example` provided; never commit
  secrets (decided).
- **Candidates, not final:** Pandas / Polars, NumPy, Scikit-learn, Sentence Transformers or
  suitable embeddings, Isolation Forest (anomaly comparison), Gemini API (initial LLM candidate),
  FastAPI (backend/API candidate).

Candidate technologies are validated during implementation and are not locked.

## 11. Evaluation Harness (Decided)

Introduced early rather than deferred to Phase 10, as a top-level `evaluation/` package. It uses
clean datasets plus **controlled corruption injection** with known ground truth to evaluate
detectors, cleaning accuracy, DCQS weights and the anti-gaming coefficient, and LLM providers.
Benchmark datasets and metrics are OPEN.

## 12. Run Artifacts and Reproducibility (Decided)

Each run lives in a top-level `runs/<run_id>/` directory with phase-specific subdirectories:

```
runs/<run_id>/
  manifest.json      run id, version, reference + SHA-256 of the original input
  input/             immutable original upload (byte-for-byte, read-only)
  profile/ detection/ scoring/ llm/ cleaning/ validation/ report/
```

- The original uploaded file is preserved as an immutable input artifact for reproducibility.
- Persisted artifacts are Pydantic models with `schema_version`.
- The validated CleaningPlan is persisted, so execution is deterministic and replayable even though
  re-querying an LLM may return a different plan. Prompt/response versioning and hashing details
  are OPEN.

## 13. Development Rules

- Build step by step; do not implement all modules at once.
- Keep modules independently testable and loosely coupled.
- Preserve raw data.
- No hardcoded/mock scoring and no fake LLM integration.
- Keep the LLM provider configurable.
- Never commit API keys.
- After each meaningful phase: test → review → fix → proceed.
- Do not skip testing or validation; do not claim checks passed unless they actually ran.
- Claude is the implementation agent. Architecture, brainstorming, review, and acceptance happen
  before moving to the next phase.

## 14. Planned Phases

| Phase | Scope |
|---|---|
| 0 | Project understanding + architecture |
| 1 | Project foundation |
| 2 | Data upload + profiler |
| 3 | DCQS scoring (after the DCQS specification open items are resolved) |
| 4 | Issue detection |
| 5 | LLM reasoning |
| 6 | Cleaning engine |
| 7 | Validation |
| 8 | Before/after reporting |
| 9 | UI + integration |
| 10 | Testing, evaluation, optimization |

The evaluation harness is built incrementally from early phases onward, not only in Phase 10.

## 15. Current Status

- Core architecture and V2 decisions are approved for development planning.
- Phase 1 (project foundation) is implemented and accepted: packaging, configuration, Pydantic
  schema foundation, run/artifact store, logging, test foundation, `evaluation/` scaffold. It was
  verified by GitHub Actions on Windows with Python 3.11.9 and 3.13.17 (70 tests, Ruff, mypy
  strict), at commit `56f049c`.
- Phase 2 (data ingestion and profiling) is in progress. No Phase 3 or later functionality
  exists yet.

## 16. Open Items

Nothing here is decided. Each must be resolved and recorded in this document before the phase that
depends on it.

**Before Phase 3 (DCQS specification)**

1. Formulas for Categorical, Numerical/Unit, Value Validity, Schema, and Anomaly dimensions.
2. Definition of "eligible cells" for completeness (optional columns, fully empty columns, etc.).
3. Dimension overlap: how one cell issue is attributed across Type, Format, and Validity so it is
   not penalized multiple times.
4. Type-inference rule when no UserRules exist (dominant type and threshold).
5. Null-token handling, including how `"unknown"` is treated.
6. Meaning of "handled" for anomalies that are flagged but not changed, including behavior in
   non-interactive mode.
7. Anti-gaming beyond row deletion (nulling invalid cells, over-merging categories, lossy
   coercion), the treatment of legitimate approved duplicate removal, and the penalty coefficient
   (to be calibrated).
8. Weight calibration and N/A rules per dimension.

**Before Phase 2 / during implementation**

9. Ingestion contract details: encodings, delimiters, header-row detection, merged cells, and
   file/row limits.
10. Dataset handle / Pandas vs Polars decision.

**Before the relevant phase**

11. UserRules format.
12. Detection: near-duplicate and category-similarity methods; ambiguous date/number parsing
    policy.
13. CleaningPlan: closed action list, step ordering, idempotence, and ChangeLog row identity/scale.
14. Risk/Review gate: confidence and risk thresholds.
15. Validation: explicit status criteria, thresholds, and rollback granularity.
16. LLM: provider selection (benchmark), prompt versioning/hashing, masking rules.
17. Evaluation: benchmark datasets, corruption types, and metrics.
18. Output safety (e.g. spreadsheet formula injection on export).
