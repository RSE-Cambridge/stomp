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
	@(cd ../app-tests/cgyro && ./run.sh)
	@echo
	@(cd ../app-tests/ukca && ./run.sh)
	@echo


.PHONY: clean
clean:
	@make -s -C ../benchmarks clean
	@make -s -C ../examples clean
	@make -s -C ../app-tests/cgyro clean
	@(cd ../app-tests/ukca && ./clean.sh)
