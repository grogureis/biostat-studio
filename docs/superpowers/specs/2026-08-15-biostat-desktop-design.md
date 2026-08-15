# BioStat Studio — Desktop Application Design

**Date:** 2026-08-15  
**Target:** Apple Silicon macOS (M-series, including M5)  
**Default language:** English, with full Turkish output support  
**Privacy model:** Fully local and offline

## 1. Purpose

BioStat Studio is a standalone macOS desktop application for planning, running, reviewing, and reporting biostatistical analyses. A researcher supplies a dataset, research question, hypotheses, and study-design details. The application validates those inputs, proposes a justified analysis plan, waits for scientific approval, executes the analysis, and generates a publication-ready Word Results section with tables and figures.

The application is independent of Codex and any cloud service. Patient and research data never leave the user's Mac.

## 2. Success Criteria

The first production release must:

1. Launch by double-clicking a macOS application icon without requiring a separate Python installation.
2. Import Excel as the primary format and CSV/SPSS as secondary formats.
3. Accept research questions and hypotheses through structured forms or imported Word/PDF text.
4. Detect variable types and require the user to confirm study design and variable roles.
5. Produce an editable, justified analysis plan before running any analysis.
6. Execute approved statistical and machine-learning workflows with assumption, leakage, and sample-size safeguards.
7. Present interpretable results, diagnostics, tables, and publication-quality figures inside the application.
8. Export a polished `.docx` Results section in English by default or Turkish on request.
9. Save a reproducible local project containing inputs, decisions, transformations, versions, warnings, and outputs.

## 3. Product Scope

### 3.1 Main project workflow

The interface uses a six-stage project flow:

1. **Study brief:** research question, hypotheses, design, population, endpoints, and language.
2. **Data and variables:** file import, sheet selection, validation, variable dictionary, roles, coding, and exclusions.
3. **Analysis plan:** proposed primary/secondary analyses, assumptions, alternatives, multiplicity handling, and planned outputs.
4. **Run and diagnose:** execution progress, warnings, diagnostics, sensitivity analyses, and reproducibility information.
5. **Results review:** narrative, effect estimates, uncertainty, tables, figures, and editable scientific notes.
6. **Word report:** export options, report preview, and final `.docx` generation.

An optional automatic mode may accept and run a plan in one action, but the standard workflow retains the scientific approval checkpoint.

### 3.2 Statistical coverage

The integrated analysis workflow includes:

- descriptive summaries and distribution diagnostics;
- missingness and data-quality assessment;
- parametric and nonparametric independent/paired comparisons;
- ANOVA-family and rank-based multi-group comparisons with post-hoc procedures;
- chi-square and exact categorical tests;
- Pearson and Spearman correlation;
- linear, binary logistic, ordinal, multinomial, and count regression where data support them;
- repeated-measures analysis and mixed-effects models;
- Kaplan–Meier estimation, log-rank tests, and Cox regression;
- ROC/AUC analysis and calibration;
- effect sizes, confidence intervals, multiplicity corrections, and sensitivity analyses;
- missing-data methods appropriate to the analysis and available information.

Power/sample-size calculation and meta-analysis are separate tools within the application because their inputs and workflows differ from dataset-driven project analysis.

### 3.3 Machine-learning coverage

The application supports tabular biomedical classification, regression, and exploratory clustering. Candidate workflows include regularized generalized linear models, tree ensembles, gradient boosting, support-vector methods, nearest-neighbor methods, and suitable clustering algorithms.

Machine-learning evaluation must:

- keep preprocessing and feature selection inside validation folds;
- detect likely target leakage and identifier leakage;
- use stratification or grouping when the study design requires it;
- support nested cross-validation when tuning and unbiased comparison are both requested;
- report uncertainty and out-of-fold metrics instead of training performance;
- evaluate discrimination, calibration, and clinically meaningful threshold metrics;
- flag insufficient sample or event counts;
- expose model settings, random seeds, and selected features;
- provide model-appropriate feature importance and local/global explanations without implying causality.

## 4. Architecture

### 4.1 Desktop shell

Electron provides the signed-capability-ready macOS application shell, native file dialogs, application menu, project lifecycle, localization, and the Clinical Calm interface. The renderer has no direct operating-system access. Privileged actions are exposed through a narrow, typed preload bridge.

### 4.2 Local analysis service

A bundled Apple Silicon Python runtime hosts the scientific engine. Core libraries include pandas, SciPy, statsmodels, scikit-learn, lifelines, matplotlib/seaborn, openpyxl, python-docx, and compatible readers for supported formats.

Electron starts the service on loopback using an ephemeral port and per-session authentication token. The service rejects unauthenticated requests and non-loopback origins. It is terminated when the application exits. No externally reachable listener or telemetry is enabled.

Long analyses use job identifiers, progress events, cancellation, and structured logs so the interface remains responsive.

### 4.3 Scientific modules

The Python application is split into independently testable modules:

- `data_intake`: file reading, schema inference, validation, and immutable source handling;
- `study_model`: structured research question, hypotheses, design, and variable roles;
- `planner`: deterministic analysis selection, rationale, prerequisites, alternatives, and output contract;
- `analyses`: statistical method implementations using common result objects;
- `ml`: leakage-safe pipelines, validation, tuning, interpretation, and comparison;
- `visuals`: accessible, publication-quality figure generation;
- `reporting`: bilingual narrative, tables, captions, and Word assembly;
- `projects`: local persistence, audit trail, versions, and export bundles;
- `service`: authenticated API, jobs, progress, cancellation, and errors.

### 4.4 Analysis-plan contract

Free text is not treated as sufficient evidence for a statistical decision. The planner combines research-question text with confirmed structured metadata: study design, outcome type, predictors/exposures, group structure, pairing/repeated measurements, time-to-event fields, covariates, and analysis intent.

Every proposed plan item contains:

- estimand or analytical objective;
- chosen method and rationale;
- required variables and inclusion set;
- assumptions and planned checks;
- alternative or robust method;
- multiplicity strategy;
- effect size and uncertainty to report;
- required tables and figures;
- blocking errors and non-blocking warnings.

Users may edit the plan. Every edit is recorded in the project audit trail.

## 5. Data Flow and Persistence

1. The source file is opened read-only and fingerprinted; it is never modified.
2. A local project stores metadata and relative references to generated artifacts.
3. Import creates a typed data snapshot and data-quality report.
4. Confirmed study metadata is converted into a versioned plan.
5. The analysis job consumes the exact data and plan versions and writes structured results.
6. Tables, figures, and narrative are derived from the same structured result objects.
7. Export records the report language, application/library versions, execution time, seeds, transformations, exclusions, and warnings.

Projects are portable local folders or packages. Autosave is atomic, recoverable, and never overwrites the original dataset.

## 6. Reporting Design

The default report is journal-neutral and biomedical. It contains a `Results` heading, concise results prose, numbered tables and figures with captions, effect estimates, 95% confidence intervals, exact p-values, sample sizes, missing-data notes, and material sensitivity findings. It avoids causal wording unless the design and model justify it.

English is the default. Turkish changes narrative, headings, captions, footnotes, decimal conventions where appropriate, and explanatory labels; statistical symbols remain conventional. The result values and analysis decisions are identical across languages.

Figures are exported as high-resolution PNG and vector SVG where compatible. Palettes are color-vision-safe, labels are readable at journal column widths, and captions remain understandable without the surrounding prose.

The `.docx` generator uses a restrained publication style, stable heading hierarchy, repeating table headers, controlled page breaks, figure alt text, and editable Word-native text/tables. A report preview is shown before export.

## 7. User Interface

The approved **Clinical Calm** visual direction uses warm white surfaces, deep clinical green navigation, restrained terracotta actions, readable serif display type, and a calm information density suitable for long research sessions.

The primary layout has:

- a top bar showing project, offline status, language, save state, and global actions;
- a left six-step workflow rail;
- a central task-focused workspace;
- a right scientific inspector for assumptions, warnings, explanations, and approval actions.

Critical warnings are never communicated by color alone. Tables, forms, keyboard navigation, focus states, and charts follow accessibility requirements.

## 8. Error Handling and Scientific Guardrails

Errors are classified as:

- **blocking data errors:** unreadable files, missing required variables, invalid event/time coding, or unusable outcomes;
- **blocking scientific errors:** method incompatible with design or insufficient usable observations;
- **review warnings:** influential points, poor model fit, sparse cells, convergence concerns, imbalance, or assumption violations;
- **informational notes:** transformations, defaults, approximations, and software limitations.

The interface explains what occurred, why it matters, and how to resolve it. Failed jobs preserve logs and partial diagnostics without presenting incomplete results as valid. Numerical warnings and convergence failures propagate into the plan, results view, and report.

The product explicitly states that automated analysis supports, but does not replace, qualified statistical review. It never invents values, imputes silently, or suppresses unfavorable findings.

## 9. Verification Strategy

### 9.1 Scientific correctness

- unit tests against published examples and trusted package outputs;
- regression fixtures with known estimates, intervals, statistics, and edge cases;
- property tests for invariants such as row-order stability and language-independent results;
- comparison of selected workflows with independently generated R/Python reference outputs;
- explicit tests for leakage, fold isolation, grouped data, sparse events, and convergence failures.

### 9.2 Application quality

- typed API contract tests between Electron and Python;
- end-to-end tests for import, plan approval, cancellation, save/reopen, and report export;
- corrupted-file, missing-sheet, and interrupted-job recovery tests;
- bilingual snapshot tests and keyboard/accessibility checks;
- Apple Silicon packaging smoke tests on a clean macOS user account.

### 9.3 Report quality

Generated Word fixtures are structurally inspected and rendered to page images. Tests verify that tables are readable, figures are not clipped, captions stay paired with content, headings are consistent, and English/Turkish outputs contain the same numerical results.

## 10. Distribution

Development and local use do not require an Apple Developer account. Initial builds produce an unsigned Apple Silicon `.app` and `.dmg`. Distribution to other users without Gatekeeper warnings is a later release step requiring Apple Developer Program membership, Developer ID signing, hardened runtime, and notarization.

No Vercel or web deployment is part of the desktop product.

## 11. Delivery Phases

1. Desktop shell, Clinical Calm workflow, project persistence, Excel intake, and authenticated local service.
2. Study model, deterministic planner, core descriptive/group/categorical/correlation/regression analyses, result contracts, and bilingual Word report.
3. Survival, repeated measures, mixed models, ROC, missingness tools, power analysis, and meta-analysis.
4. Leakage-safe machine learning, comparison, calibration, and interpretability.
5. Scientific reference validation, packaging, clean-machine verification, accessibility, signing/notarization guidance, and release hardening.

Each phase must leave the application runnable and verified. Methods are exposed in the interface only after their reference tests pass.

## 12. Explicit Non-Goals for the First Release

- cloud accounts, collaboration, telemetry, or remote storage;
- autonomous clinical decisions or treatment recommendations;
- image, genomic-sequence, or free-form signal deep learning;
- real-time multi-user editing;
- Intel macOS, Windows, or Linux distribution;
- automatic journal submission.
