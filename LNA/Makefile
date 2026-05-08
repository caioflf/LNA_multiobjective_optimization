PYTHON ?= python3

PASSIVE_NETWORK_SCRIPT := src/scripts/passive_networks.py
PASSIVE_NETWORK_MULTI_OBJECTIVE_DB := src/database/passive_networks_mim_no_varactors.json
MIM_MODELS ?= sky130_fd_pr__cap_mim_m3_2
MIM_SIZES ?= 2x2 4x4 6x6 8x8 10x10
MIM_MF_VALUES ?= 1
POLY_RESISTOR_SELECTION ?= all
PASSIVE_NETWORK_TOPOLOGY ?= rlc-parallel
PASSIVE_MAX_RESISTORS_PER_NETWORK ?=

SIMULATE_CIRCUITS_SCRIPT := src/scripts/simulate_circuits.py
OPTIMIZE_CIRCUITS_SCRIPT := src/scripts/optimize_circuits.py
CIRCUIT_OUTPUT_ROOT ?= generated_circuits

SIM_THREADS ?= 8
SIM_PRIORITY ?= high
SIM_MAX_CIRCUITS ?=
SIM_SUBSET ?=
SIM_PROGRESS ?= 1
SIM_PROGRESS_EVERY ?= 1
SIM_TIMEOUT ?=


OPT_PARTITIONS := 6
OPT_CROSSOVER_PROB := 0.9
OPT_MUTATION_PROB := 0.15
OPT_VERSION := $(OPT_PARTITIONS)_$(OPT_CROSSOVER_PROB)_$(OPT_MUTATION_PROB)
OPT_OUTPUT_ROOT := optimized_circuits_$(OPT_VERSION)
OPT_TRANSISTOR_GROUP ?= nmos
OPT_POPULATION_SIZE ?= 300
OPT_OFFSPRING_SIZE ?= 300
OPT_GENERATIONS ?= 200
OPT_F0 ?= 5e9
OPT_AC_START ?=
OPT_AC_STOP ?=
OPT_SIM_THREADS ?= 8
OPT_SIM_TIMEOUT ?= 180
OPT_DEMO_SIM_TIMEOUT ?= 120
OPT_SEED ?= 7
OPT_MAX_NF_DB ?= 10
OPT_MAX_POWER ?= 
OPT_MIN_S21_DB ?= 0
OPT_MIN_F_BW ?= 
OPT_MAX_S11_DB ?= 

ANALYSIS_RUN_ROOT ?= $(OPT_OUTPUT_ROOT)
#ANALYSIS_RUN_ROOT ?= data/02_optimized_circuits_6_0.9_0.15
ANALYSIS_OUTPUT_DIR ?= $(ANALYSIS_RUN_ROOT)/analysis/results
ANALYSIS_PLOTS_DIR ?= $(ANALYSIS_RUN_ROOT)/analysis/plots
ANALYSIS_PYTHON ?= $(PYTHON)
ANALYSIS_PLOT_PYTHON ?= /opt/homebrew/bin/python3
ANALYSIS_COLOR_BY ?= vg
ANALYSIS_TOP_COUNT ?= 100
ANALYSIS_MAX_NF_DB ?= 
ANALYSIS_MAX_POWER ?= 
ANALYSIS_MIN_GAIN_DB ?= 
ANALYSIS_MIN_F_BW ?= 
ANALYSIS_MAX_S11_DB ?= 
ANALYSIS_CLEAN_PATHS ?= $(OPT_OUTPUT_ROOT)/analysis/results \
												$(OPT_OUTPUT_ROOT)/analysis/results_* \
												$(OPT_OUTPUT_ROOT)/analysis/plots \
												$(OPT_OUTPUT_ROOT)/analysis/plots_* \
												$(OPT_OUTPUT_ROOT)/analysis/.cache \
												$(OPT_OUTPUT_ROOT)/analysis/.matplotlib-cache \
												$(OPT_OUTPUT_ROOT)/analysis/__pycache__
ANALYSIS_FILTER_ARGS = $(strip \
	$(if $(ANALYSIS_MAX_NF_DB),--max-nf-db $(ANALYSIS_MAX_NF_DB)) \
	$(if $(ANALYSIS_MAX_POWER),--max-power $(ANALYSIS_MAX_POWER)) \
	$(if $(ANALYSIS_MIN_GAIN_DB),--min-gain-db $(ANALYSIS_MIN_GAIN_DB)) \
	$(if $(ANALYSIS_MIN_F_BW),--min-f-bw $(ANALYSIS_MIN_F_BW)) \
	$(if $(ANALYSIS_MAX_S11_DB),--max-s11-db $(ANALYSIS_MAX_S11_DB)) \
)

.PHONY: all generate-passive-network-multiobjective clean-passive-network-multiobjective simulate-circuits analyze-circuits optimize-circuits optimize-circuits-demo analysis-summary analysis-export analysis-plots analysis-all clean-analysis clean-circuits

all: generate-passive-network-multiobjective

generate-passive-network-multiobjective: $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB)

$(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB): $(PASSIVE_NETWORK_SCRIPT) src/database/capacitors.py src/database/inductors.py src/database/resistors.py
	$(PYTHON) $(PASSIVE_NETWORK_SCRIPT) \
		--no-varactors \
		--mim-models $(MIM_MODELS) \
		--mim-sizes $(MIM_SIZES) \
		--mf-values $(MIM_MF_VALUES) \
		--poly-resistor-selection $(POLY_RESISTOR_SELECTION) \
		--network-topology $(PASSIVE_NETWORK_TOPOLOGY) \
		$(if $(PASSIVE_MAX_RESISTORS_PER_NETWORK),--max-resistors-per-network $(PASSIVE_MAX_RESISTORS_PER_NETWORK),) \
		--output $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB)

clean-passive-network-multiobjective:
	rm -f $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB)

simulate-circuits: $(SIMULATE_CIRCUITS_SCRIPT)
	$(PYTHON) $(SIMULATE_CIRCUITS_SCRIPT) \
		$(CIRCUIT_OUTPUT_ROOT) \
		--threads $(SIM_THREADS) \
		--priority $(SIM_PRIORITY) \
		$(if $(SIM_SUBSET),--subset $(SIM_SUBSET),) \
		$(if $(SIM_MAX_CIRCUITS),--max-circuits $(SIM_MAX_CIRCUITS),) \
		$(if $(filter 0 false no,$(SIM_PROGRESS)),--no-progress,) \
		$(if $(SIM_PROGRESS_EVERY),--progress-every $(SIM_PROGRESS_EVERY),) \
		$(if $(SIM_TIMEOUT),--timeout $(SIM_TIMEOUT),)

analyze-circuits: $(SIMULATE_CIRCUITS_SCRIPT)
	$(PYTHON) $(SIMULATE_CIRCUITS_SCRIPT) \
		$(CIRCUIT_OUTPUT_ROOT) \
		--analyze-only \
		$(if $(SIM_SUBSET),--subset $(SIM_SUBSET),) \
		$(if $(SIM_MAX_CIRCUITS),--max-circuits $(SIM_MAX_CIRCUITS),) \
		$(if $(filter 0 false no,$(SIM_PROGRESS)),--no-progress,) \
		$(if $(SIM_PROGRESS_EVERY),--progress-every $(SIM_PROGRESS_EVERY),)

optimize-circuits: $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) $(OPTIMIZE_CIRCUITS_SCRIPT)
	$(PYTHON) $(OPTIMIZE_CIRCUITS_SCRIPT) \
		--output-root $(OPT_OUTPUT_ROOT) \
		--network-database $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) \
		--transistor-group $(OPT_TRANSISTOR_GROUP) \
		--population-size $(OPT_POPULATION_SIZE) \
		--offspring-size $(OPT_OFFSPRING_SIZE) \
		--generations $(OPT_GENERATIONS) \
		--f0 $(OPT_F0) \
		$(if $(OPT_AC_START),--ac-start $(OPT_AC_START),) \
		$(if $(OPT_AC_STOP),--ac-stop $(OPT_AC_STOP),) \
		--sim-threads $(OPT_SIM_THREADS) \
		--vg-start 0.75 \
		--vg-stop 1.15 \
		--vg-step 0.025 \
		--reference-partitions $(OPT_PARTITIONS) \
		--crossover-probability $(OPT_CROSSOVER_PROB) \
		--mutation-probability $(OPT_MUTATION_PROB) \
		--gate-r-indexes 0 \
		--gate-l-indexes 1:3 \
		--gate-c-indexes 0 \
		--feedback-r-indexes 0 \
		--feedback-l-indexes 0 \
		--load-l-indexes 1:3 \
		--source-l-indexes 1:3 \
		$(if $(OPT_SIM_TIMEOUT),--sim-timeout $(OPT_SIM_TIMEOUT),) \
		$(if $(OPT_MAX_NF_DB),--max-nf-db $(OPT_MAX_NF_DB),) \
		$(if $(OPT_MAX_POWER),--max-power $(OPT_MAX_POWER),) \
		$(if $(OPT_MIN_S21_DB),--min-s21-db $(OPT_MIN_S21_DB),) \
		$(if $(OPT_MIN_F_BW),--min-f-bw $(OPT_MIN_F_BW),) \
		$(if $(OPT_MAX_S11_DB),--max-s11-db $(OPT_MAX_S11_DB),) \
		$(if $(OPT_SEED),--seed $(OPT_SEED),) \

optimize-circuits-demo: $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) $(OPTIMIZE_CIRCUITS_SCRIPT)
	$(PYTHON) $(OPTIMIZE_CIRCUITS_SCRIPT) \
		--output-root optimization_demo \
		--network-database $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) \
		--transistor-group $(OPT_TRANSISTOR_GROUP) \
		--population-size 12 \
		--offspring-size 12 \
		--generations 3 \
		--f0 $(OPT_F0) \
		$(if $(OPT_AC_START),--ac-start $(OPT_AC_START),) \
		$(if $(OPT_AC_STOP),--ac-stop $(OPT_AC_STOP),) \
		--sim-threads $(OPT_SIM_THREADS) \
		--sim-timeout $(OPT_DEMO_SIM_TIMEOUT) \
		--vg-start 0.75 \
		--vg-stop 1.15 \
		--vg-step 0.025 \
		--reference-partitions $(OPT_PARTITIONS) \
		--crossover-probability $(OPT_CROSSOVER_PROB) \
		--mutation-probability $(OPT_MUTATION_PROB) \
		--gate-r-indexes 0 \
		--gate-l-indexes 1:3 \
		--gate-c-indexes 0 \
		--feedback-r-indexes 0 \
		--feedback-l-indexes 0 \
		--source-l-indexes 1:3 \
		--load-l-indexes 1:3 \
		$(if $(OPT_MAX_NF_DB),--max-nf-db $(OPT_MAX_NF_DB),) \
		$(if $(OPT_MAX_POWER),--max-power $(OPT_MAX_POWER),) \
		$(if $(OPT_MIN_S21_DB),--min-s21-db $(OPT_MIN_S21_DB),) \
		$(if $(OPT_MIN_F_BW),--min-f-bw $(OPT_MIN_F_BW),) \
		$(if $(OPT_MAX_S11_DB),--max-s11-db $(OPT_MAX_S11_DB),) \
		--seed 1 

analysis-summary:
	$(ANALYSIS_PYTHON) analysis/summarize_optimization.py $(ANALYSIS_RUN_ROOT) --top-count $(ANALYSIS_TOP_COUNT) $(ANALYSIS_FILTER_ARGS)

analysis-export:
	$(ANALYSIS_PYTHON) analysis/summarize_optimization.py $(ANALYSIS_RUN_ROOT) --output-dir $(ANALYSIS_OUTPUT_DIR) --top-count $(ANALYSIS_TOP_COUNT) $(ANALYSIS_FILTER_ARGS)

analysis-plots:
	$(ANALYSIS_PLOT_PYTHON) analysis/plot_optimization.py $(ANALYSIS_RUN_ROOT) --output-dir $(ANALYSIS_PLOTS_DIR) --color-by $(ANALYSIS_COLOR_BY) $(ANALYSIS_FILTER_ARGS)

analysis-all: analysis-export analysis-plots

clean-analysis:
	rm -rf $(ANALYSIS_CLEAN_PATHS)


clean-circuits:
	rm -rf $(CIRCUIT_OUTPUT_ROOT) 

clean-optimization:
	rm -rf $(OPT_OUTPUT_ROOT)
