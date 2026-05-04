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
OPT_OUTPUT_ROOT ?= optimized_circuits
OPT_TRANSISTOR_GROUP ?= all
OPT_POPULATION_SIZE ?= 24
OPT_OFFSPRING_SIZE ?= 24
OPT_GENERATIONS ?= 10
OPT_F0 ?= 5e9
OPT_SIM_TIMEOUT ?=
OPT_DEMO_SIM_TIMEOUT ?= 120
OPT_SEED ?=

.PHONY: all generate-passive-network-multiobjective clean-passive-network-multiobjective simulate-circuits analyze-circuits optimize-circuits optimize-circuits-demo clean-circuits

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
		$(if $(OPT_SIM_TIMEOUT),--sim-timeout $(OPT_SIM_TIMEOUT),) \
		$(if $(OPT_SEED),--seed $(OPT_SEED),)

optimize-circuits-demo: $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) $(OPTIMIZE_CIRCUITS_SCRIPT)
	$(PYTHON) $(OPTIMIZE_CIRCUITS_SCRIPT) \
		--output-root optimized_circuits_demo \
		--network-database $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) \
		--transistor-group nmos_and_lvt \
		--vg-values 0.7 0.8 0.9 1.0 \
		--population-size 12 \
		--offspring-size 12 \
		--generations 3 \
		--f0 $(OPT_F0) \
		--sim-timeout $(OPT_DEMO_SIM_TIMEOUT) \
		--seed 1 \
		--gate-r-indexes 0 \
		--gate-l-indexes 1:3 \
		--gate-c-indexes 0 \
		--feedback-r-indexes 0 \
		--feedback-l-indexes 0 \
		--feedback-c-indexes 0 \
		--source-l-indexes 1:3 \
		--load-l-indexes 1:3 

clean-circuits:
	rm -rf $(CIRCUIT_OUTPUT_ROOT)
