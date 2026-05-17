# AndroCT Auxiliary Replication Plan after Main 55-Job Run

Date: 2026-05-16

## Goal

After the AndroCT second-main-dataset 55-job protocol finishes and all results are pulled to `G:\`, run an auxiliary experiment phase that mirrors the KronoDroid auxiliary evidence as closely as possible. The purpose is to make AndroCT a true second main dataset rather than only an external validation set.

## Execution Order

1. Finish the current AndroCT second-main run.
   - Expected jobs: 55 summary files.
   - Scope: yearly 2010-2019 for K=1/2/3/5/10 plus pooled 2010-2019 for K=1/2/3/5/10.
   - Do not start auxiliary jobs before the 55-job run is complete unless the server is clearly idle.

2. Pull the completed main-run package to local G drive.
   - Target pattern: `G:\AndroCT_second_main_results_hzt3_YYYYMMDD_HHMMSS`
   - Include remote outputs, logs, scripts, experiment code, and cache metadata when reasonably sized.
   - Also copy relevant local scripts from `F:\work\submissions\network_agent_safety\scripts`.

3. Inventory KronoDroid auxiliary experiments.
   - Locate existing KronoDroid result folders, scripts, tables, and paper references.
   - Extract exact auxiliary protocols before launching AndroCT copies.
   - Record any protocol that cannot be exactly matched because of dataset-specific feature availability.

4. Deploy AndroCT auxiliary phase.
   - Remote directory: `/root/experiments/androct_auxiliary`
   - Reuse the verified AndroCT data symlink or validated data copy.
   - Do not delete or overwrite the completed main-run outputs.

## Auxiliary Experiment Blocks

### B1. Source-plus-support warm-start baseline

Replicate the KronoDroid auxiliary baseline that trains on source data plus the small target support set. Compare against support-selection/SGFE variants under the same year, direction, K, and seed settings.

Primary outputs:
- BA, macro-F1, accuracy by year, direction, K, seed.
- Mean/std and paired comparison against SGFE and source-CV softmax.

### B2. Stronger all-feature baselines

Replicate stronger conventional classifiers used as KronoDroid auxiliary evidence, subject to installed dependencies and runtime cost.

Candidate baselines:
- RandomForest or ExtraTrees when already available through scikit-learn.
- Gradient boosting only if the required package is already installed or installation is explicitly approved.

Primary purpose:
- Test whether the claimed runtime-shift failure is only due to a weak classifier.

### B3. Adaptation diagnostics

Replicate KronoDroid adaptation-style diagnostics where feasible.

Candidate diagnostics:
- CORAL-style tabular alignment if present in existing code.
- DANN or neural adaptation only if KronoDroid code already contains a runnable implementation.

Primary purpose:
- Show whether unsupervised adaptation alone resolves emulator-real or real-emulator shifts.

### B4. Label-noise and support corruption stress

Extend the existing true-vs-permuted support evidence into a controlled auxiliary stress test.

Settings:
- True support labels.
- Permuted support labels.
- Optional partial corruption levels if KronoDroid used them.

Primary purpose:
- Demonstrate whether gains depend on real target support signal rather than leakage or random support sampling.

### B5. Feature-group and overlap diagnostics

Replicate KronoDroid feature-group auxiliary analysis.

Settings:
- Fixed groups: android_api, java_api, intent, all-platform.
- Source-CV selected group.
- Top-1 support-selected group.
- Group stability across years, directions, and K.

Primary purpose:
- Explain when AndroCT agrees with or differs from KronoDroid.

### B6. Statistical and paper-facing summaries

After auxiliary jobs finish:
- Generate tables aligned with KronoDroid auxiliary tables.
- Run paired tests where seed-level paired results exist.
- Create compact CIKM-ready figures/tables.
- Separate strong claims, partial claims, and unsupported claims.

## Success Criteria

The auxiliary phase is complete only when:
- Main AndroCT run has 55 valid `summary.csv` files.
- Main results and logs are pulled to `G:\`.
- KronoDroid auxiliary protocols are inventoried.
- AndroCT auxiliary results are saved with logs and scripts.
- A paper-facing summary identifies which auxiliary findings are safe to write into the CIKM manuscript.

## Current Status at Plan Creation

As of the latest check, the AndroCT second-main run had:
- 50/55 summary files.
- 5 pooled jobs still running.
- 0 known failures.
- 44/44 AndroCT tar.gz files present on the server.

