.PHONY: smoke paper-check artifact-check mapper-smoke reference-run chia-smoke codesign-search test clean

CC ?= cc
CFLAGS ?= -O3 -std=c11 -Wall -Wextra -Werror
PYTHON ?= python3
BUILD_DIR := build
SMOKE_BIN := $(BUILD_DIR)/fmcw_smoke

$(SMOKE_BIN): workload/fmcw.c workload/fmcw.h workload/fmcw_smoke.c
	@mkdir -p $(BUILD_DIR)
	$(CC) $(CFLAGS) -Iworkload workload/fmcw.c workload/fmcw_smoke.c -lm -o $@

smoke: $(SMOKE_BIN)
	$(SMOKE_BIN)

paper-check:
	$(PYTHON) scripts/check_paper_results.py

artifact-check: smoke paper-check

mapper-smoke:
	PYTHONPATH=src $(PYTHON) -m chia_maco.cli evaluate-all

reference-run:
	PYTHONPATH=src $(PYTHON) -m chia_maco.cli reference-run

chia-smoke:
	RAY_NODE_IP_ADDRESS=127.0.0.1 PYTHONPATH=src $(PYTHON) -m chia_maco.cli chia-smoke

codesign-search:
	RAY_NODE_IP_ADDRESS=127.0.0.1 PYTHONPATH=src $(PYTHON) -m chia_maco.cli codesign-search

test: $(SMOKE_BIN)
	PYTHONPATH=src $(PYTHON) -m pytest -q

clean:
	rm -rf $(BUILD_DIR)
