# AndroCT auxiliary experiment record

This directory records the AndroCT second-main-dataset and auxiliary experiment
code used for the CIKM 2026 network-agent-safety manuscript work.

The code is included for reproducibility and process traceability. It does not
include raw datasets, server passwords, Feishu webhooks, API tokens, or large
experiment outputs.

## Layout

- `scripts/run_androct_sgfe_experiment.py`
  - Main AndroCT support-gated feature-group experiment.
  - Produces yearly and pooled `*_summary.csv` / `*_summary.md` outputs.

- `scripts/run_androct_auxiliary_experiments.py`
  - AndroCT auxiliary checks mirroring the KronoDroid reviewer-control suite.
  - Includes source-plus-support warm-start, all-feature support selection,
    support-only target baselines, label-noise support stress, and SVD-CORAL.

- `scripts/launch_androct_auxiliary_hzt3.sh`
  - Original auxiliary queue launcher for 55 formal tasks.

- `scripts/accelerate_androct_pooled_hzt3.sh`
  - Replaces the slow pooled monolithic tail with shard-based execution.

- `scripts/launch_androct_auxiliary_pooled_shards_hzt3.sh`
  - Runs pooled `K x split x seed` shards with bounded parallelism.

- `scripts/merge_androct_auxiliary_shards.py`
  - Merges 20 pooled shards for each K back into the formal pooled output
    directory so the final accounting remains 55 formal summaries.

- `scripts/monitor_androct_auxiliary_hzt3.sh`
  - Lightweight remote monitor for tmux sessions, logs, and summary counts.

- `scripts/pull_androct_auxiliary_results_hzt3.ps1`
  - Pulls final auxiliary outputs/logs/scripts/state into the local G-drive
    CIKM working package.

- `docs/`
  - Experiment plans, protocol-alignment notes, and step-by-step process log.

## Remote convention

The scripts assume the following remote directories when run on the MatPool
server used in the experiment:

- Main AndroCT run: `/root/experiments/androct_second_main`
- Auxiliary run: `/root/experiments/androct_auxiliary`
- Shared Python environment: `/root/experiments/androct_sgfe/.venv`

The local workflow used an SSH key outside this repository. No private key,
password, webhook, or token is stored here.

For scripts that need SSH access, set environment variables such as
`MATPOOL_SSH_KEY`, or replace placeholder host/port values in a private local
copy. Do not commit credentials.

## Current status captured in docs

The process record notes:

- The 55-task AndroCT second-main experiment completed and was synced locally.
- The auxiliary run completed all 50 yearly tasks.
- The five pooled tasks were converted from slow monolithic jobs into
  shard-based execution.
- `MAX_PARALLEL=6` caused an exit-137 memory failure on one shard, so the safe
  pooled-shard setting was reduced to `MAX_PARALLEL=4`.
