#!/bin/bash

.PHONY: test
test:
	@echo Running ruff
	@echo ============
	@(cd .. && ruff check)
	@echo
	@echo Running pytest
	@echo ==============
	@(cd .. && pytest -q -n 4)
	@echo
	@(cd ../benchmarks && ./run-drb.sh)
	@echo
	@(cd ../examples && ./run-all.sh)
	@echo

.PHONY: clean
clean:
	@make -C ../benchmarks clean
	@make -C ../examples clean
