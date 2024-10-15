# Default number of cores.
CORES = 6

# Set the default build destination when running gem5 Python scripts.
CMD_ALL = "./build/ALL/gem5.opt"
CMD_X86 = "./build/X86/gem5.opt"

# Print help.
.PHONY: help
help:
	@echo "Usage: make <command>"
	@echo "Possible commands:"
	@echo "    build                           Alias for 'build-x86'."
	@echo "    build-x86                       Build gem5 for x86 target, 'opt' build variant."
	@echo "    build-all                       Build gem5 for ALL target, 'opt' build variant."
	@echo "    help                            Show this message."
	@echo "    run script=<script-name>        Alias for 'run-x86'."
	@echo "    run-all script=<script-name>    Run gem5 with the ALL build. You must specify a Python script to run."
	@echo "    run-x86 script=<script-name>    Run gem5 with the x86 build. You must specify a Python script to run."

.DEFAULT_GOAL := help

# 'build' is an alias for 'build-x86.'
.PHONY: build
build: build-x86

# Build gem5 for ALL target, 'opt' build variant.
.PHONY: build-all
build-all:
	scons build/ALL/gem5.opt -j$(CORES)

# Build gem5 for x86 target, 'opt' build variant.
.PHONY: build-x86
build-x86:
	scons build/X86/gem5.opt -j$(CORES)

# 'run' is an alias for 'run-x86.'
.PHONY: run
run: run-x86

# Run gem5 with the ALL build. You must specify a Python script to run.
.PHONY: run-all
run-all:
	@if [ -z "$(script)" ]; then\
		echo "Error: No script specified.";\
		exit 0;\
	fi;\
	echo "$(CMD_ALL) $(script)";\
	$(CMD_ALL) $(script)

# Run gem5 with the x86 build. You must specify a Python script to run.
.PHONY: run-x86
run-x86:
	@if [ -z "$(script)" ]; then\
		echo "Error: No script specified.";\
		exit 0;\
	fi;\
	echo "$(CMD_X86) $(script)";\
	$(CMD_X86) $(script)
