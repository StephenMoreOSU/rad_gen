
## Command to remove all golden result jsons
# find tests/ -type d -name "golden_results" -print0 |  xargs -0 -I{} find '{}' -name '*.json' -print0 | xargs -0 rm

# Must run ``source env_setup.sh`` prior to this

RG_HOME := $(RAD_GEN_HOME)
TESTS_DIR := tests
TESTS_SCRIPTS_DIR := $(TESTS_DIR)/scripts

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


.PHONY: clean conf-init-update-test prune-update-conda-env
