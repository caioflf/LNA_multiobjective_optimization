# Optimization Analysis

These scripts analyze optimizer outputs without modifying the optimization flow.
They read `optimization_history.jsonl` as a snapshot, so they can be used after
a run finishes or while a run is still appending results.

Run the analysis through `make` from the repository root.

Print a summary only:

```sh
make analysis-summary
```

Export CSV/JSON reports:

```sh
make analysis-export
```

Create metric-pair PNG plots:

```sh
make analysis-plots
```

Export reports and plots:

```sh
make analysis-all
```

Remove generated analysis reports, plots, and local analysis caches:

```sh
make clean-analysis
```

Use a different optimization run or output location:

```sh
make analysis-all \
  ANALYSIS_RUN_ROOT=optimized_circuits \
  ANALYSIS_OUTPUT_DIR=analysis/results \
  ANALYSIS_PLOTS_DIR=analysis/plots
```

Apply post-processing filters:

```sh
make analysis-all \
  ANALYSIS_MIN_S21_DB=0 \
  ANALYSIS_MAX_S11_DB=-10 \
  ANALYSIS_MAX_NF_DB=5 \
  ANALYSIS_MAX_POWER_DBM=5 \
  ANALYSIS_MIN_F_BW=1
```

Available Make parameters:

- `ANALYSIS_RUN_ROOT`: optimization output directory to read. Default: current `OPT_OUTPUT_ROOT`.
- `ANALYSIS_OUTPUT_DIR`: CSV/JSON report directory. Default: `$(ANALYSIS_RUN_ROOT)/analysis/results`.
- `ANALYSIS_PLOTS_DIR`: PNG plot directory. Default: `$(ANALYSIS_RUN_ROOT)/analysis/plots`.
- `ANALYSIS_PYTHON`: Python used for summaries/exports. Default: `python3`.
- `ANALYSIS_PLOT_PYTHON`: Python used for matplotlib plots. Default: `/opt/homebrew/bin/python3`.
- `ANALYSIS_COLOR_BY`: plot color axis. Use metrics (`NF_db`, `NFmin_db`, `power_dBm`, `S21_db`, `F_BW`, `S11_db`), transistor values/indexes (`vg`, `wtot_um`, `length_um`, `device_type_index`, `vt_index`, `wtot_index`, `length_index`), or passive indexes like `gate_l_index`, `source_l_index`, `load_c_index`, `feedback_c_index`. Short forms like `feedback_c` also work. Default: `vg`.
- `ANALYSIS_TOP_COUNT`: number of ranked candidates to export. Default: `1000`.
- `ANALYSIS_MAX_NF_DB`: keep records with `NF_db <= value`.
- `ANALYSIS_MAX_POWER_DBM`: keep records with `power_dBm <= value`.
- `ANALYSIS_MAX_POWER`: alias for `ANALYSIS_MAX_POWER_DBM`.
- `ANALYSIS_MIN_S21_DB`: keep records with `S21_db >= value`.
- `ANALYSIS_MIN_F_BW`: keep records with `F_BW >= value`.
- `ANALYSIS_MAX_S11_DB`: keep records with `S11_db <= value`.
- `ANALYSIS_CLEAN_PATHS`: paths removed by `make clean-analysis`. Default: generated `analysis/results*`, `analysis/plots*`, and analysis cache folders.

The summarizer writes these files when `ANALYSIS_OUTPUT_DIR` is used:

- `evaluations.csv`
- `valid_evaluations.csv`
- `filtered_valid_evaluations.csv`
- `pareto_front.csv`
- `filtered_pareto_front.csv`
- `shortlist.csv`
- `shortlist.json`
- `ranked_candidates.csv`
- `ranked_candidates.json`
- `report.json`

The plot script writes PNG files to `ANALYSIS_PLOTS_DIR` and requires
`matplotlib`. On this machine, `/opt/homebrew/bin/python3` already has
matplotlib available.
