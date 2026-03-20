
## Command to remove all golden result jsons
# find tests/ -type d -name "golden_results" -print0 |  xargs -0 -I{} find '{}' -name '*.json' -print0 | xargs -0 rm

# Must run ``source env_setup.sh`` prior to this

RG_HOME := $(RAD_GEN_HOME)
TESTS_DIR := tests
TESTS_SCRIPTS_DIR := $(TESTS_DIR)/scripts

# ALU tests including VLSI sweep
run-alu-tests:
	mkdir -p tests/logs
	pytest tests/test_alu_vlsi_sweep.py -s --disable-warnings 2&>1 | tee tests/logs/alu.log

# NoC tests including RTL sweep
run-noc-tests:
	mkdir -p tests/logs
	pytest tests/test_noc_rtl_sweep.py -s --disable-warnings 2&>1 | tee tests/logs/noc.log

# SRAM tests
run-sram-tests:
	mkdir -p tests/logs
	pytest tests/test_sram_gen.py -s --disable-warnings 2&>1 | tee tests/logs/sram.log

prune-update-conda-env:
	@echo "Re loading conda env from yml file and pruning non existing packages"
	conda env update -f $(RG_HOME)/conda_env/env.yml --prune


conf-init-update-test:
	@echo "Setting new struct init test golden results"
	python3 $(TESTS_SCRIPTS_DIR)/update_golden_results.py --struct_init 
	@echo "Running tests that must pass if previous step was successful"
	pytest tests/ -m "init" --disable-warnings

# Remove all the hammer-vlsi.log files
clean:
	rm hammer-vlsi*.log

.PHONY: clean run-alu-tests run-noc-tests run-sram-tests conf-init-update-test prune-update-conda-env
