# Default number of cores.
CORES = 7

# Set the default build destination when running gem5 Python config files.
CMD_ALL_PREFIX = "./build/ALL/gem5."
CMD_X86_PREFIX = "./build/X86/gem5."

SCONS = scons
SCONS_OPTS = --install-hooks

# Print help.
.PHONY: help
help:
	@echo "Usage: make <command>"
	@echo "Possible commands:"
	@echo "  Building:"
	@echo "    build                               Alias for 'build-x86'."
	@echo "    build-all                           Alias for 'build-all-opt'."
	@echo "    build-all-fast                      Build gem5 for ALL target, 'fast' build variant."
	@echo "    build-all-opt                       Build gem5 for ALL target, 'opt' build variant."
	@echo "    build-all-debug                     Build gem5 for ALL target, 'debug' build variant."
	@echo "    build-x86                           Alias for 'build-x86-opt'."
	@echo "    build-x86-fast                      Build gem5 for x86 target, 'fast' build variant."
	@echo "    build-x86-opt                       Build gem5 for x86 target, 'opt' build variant."
	@echo "    build-x86-debug                     Build gem5 for x86 target, 'debug' build variant."
	@echo
	@echo "  Running:"
	@echo "    run config=<config-name>            Alias for 'run-x86'."
	@echo "    run-all config=<config-name>        Alias for 'run-all-opt'."
	@echo "    run-all-fast config=<config-name>   Run gem5 with the ALL 'fast' build. You must specify a Python config file to run."
	@echo "    run-all-opt config=<config-name>    Run gem5 with the ALL 'opt' build. You must specify a Python config file to run."
	@echo "    run-all-debug config=<config-name>  Run gem5 with the ALL 'debug' build. You must specify a Python config file to run."
	@echo "    run-x86 config=<config-name>        Alias for 'run-x86-opt'."
	@echo "    run-x86-fast config=<config-name>   Run gem5 with the x86 'fast' build. You must specify a Python config file to run."
	@echo "    run-x86-opt config=<config-name>    Run gem5 with the x86 'opt' build. You must specify a Python config file to run."
	@echo "    run-x86-debug config=<config-name>  Run gem5 with the x86 'debug' build. You must specify a Python config file to run."
	@echo
	@echo "  Miscellaneous:"
	@echo "    clean                           Clean all build files."
	@echo "    bell                            Produce a bell. Can be used as an alert after build completion, etc."
	@echo "    help                            Show this message."


.DEFAULT_GOAL := help

# 'build' is an alias for 'build-x86'.
.PHONY: build
build: build-x86

# 'build-all' is an alias for 'build-all-opt'.
.PHONY: build-all
build-all: build-all-opt

# Build gem5 for ALL target, 'fast' build variant.
.PHONY: build-all-fast
build-all-fast:
	$(SCONS) $(SCONS_OPTS) build/ALL/gem5.fast -j$(CORES)

# Build gem5 for ALL target, 'opt' build variant.
.PHONY: build-all-opt
build-all-opt:
	$(SCONS) $(SCONS_OPTS) build/ALL/gem5.opt -j$(CORES)

# Build gem5 for ALL target, 'debug' build variant.
.PHONY: build-all-debug
build-all-debug:
	$(SCONS) $(SCONS_OPTS) build/ALL/gem5.debug -j$(CORES)

# 'build-x86' is an alias for 'build-x86-opt'.
.PHONY: build-x86
build-x86: build-x86-opt

# Build gem5 for x86 target, 'fast' build variant.
.PHONY: build-x86-fast
build-x86-fast:
	$(SCONS) $(SCONS_OPTS) build/X86/gem5.fast -j$(CORES)

# Build gem5 for x86 target, 'opt' build variant.
.PHONY: build-x86-opt
build-x86-opt:
	$(SCONS) $(SCONS_OPTS) build/X86/gem5.opt -j$(CORES)

# Build gem5 for x86 target, 'debug' build variant.
.PHONY: build-x86-debug
build-x86-debug:
	$(SCONS) $(SCONS_OPTS) build/X86/gem5.debug -j$(CORES)


# 'run' is an alias for 'run-x86.'
.PHONY: run
run: run-x86

# 'run-all' is an alias for 'run-all-opt'.
.PHONY: run-all
run-all: run-all-opt

# Run gem5 with the ALL 'fast' build. You must specify a Python config file to run.
.PHONY: run-all-fast
run-all-fast:
	@if [ -z "$(config)" ]; then\
		echo "Error: No config file specified.";\
		exit 0;\
	fi;\
	echo "$(CMD_ALL_PREFIX)fast $(config)";\
	$(CMD_ALL_PREFIX)fast $(config)

# Run gem5 with the ALL 'opt' build. You must specify a Python config file to run.
.PHONY: run-all-opt
run-all-opt:
	@if [ -z "$(config)" ]; then\
		echo "Error: No config file specified.";\
		exit 0;\
	fi;\
	echo "$(CMD_ALL_PREFIX)opt $(config)";\
	$(CMD_ALL_PREFIX)opt $(config)

# Run gem5 with the ALL 'debug' build. You must specify a Python config file to run.
.PHONY: run-all-debug
run-all-debug:
	@if [ -z "$(config)" ]; then\
		echo "Error: No config file specified.";\
		exit 0;\
	fi;\
	echo "$(CMD_ALL_PREFIX)debug $(config)";\
	$(CMD_ALL_PREFIX)debug $(config)

# 'run-x86' is an alias for 'run-x86-opt'.
.PHONY: run-x86
run-x86: run-x86-opt

# Run gem5 with the x86 'fast' build. You must specify a Python config file to run.
.PHONY: run-x86-fast
run-x86-fast:
	@if [ -z "$(config)" ]; then\
		echo "Error: No config file specified.";\
		exit 0;\
	fi;\
	echo "$(CMD_X86_PREFIX)fast $(config)";\
	$(CMD_X86_PREFIX)fast $(config)

# Run gem5 with the x86 'opt' build. You must specify a Python config file to run.
.PHONY: run-x86-opt
run-x86-opt:
	@if [ -z "$(config)" ]; then\
		echo "Error: No config file specified.";\
		exit 0;\
	fi;\
	echo "$(CMD_X86_PREFIX)opt $(config)";\
	$(CMD_X86_PREFIX)opt $(config)

# Run gem5 with the x86 'debug' build. You must specify a Python config file to run.
.PHONY: run-x86-debug
run-x86-debug:
	@if [ -z "$(config)" ]; then\
		echo "Error: No config file specified.";\
		exit 0;\
	fi;\
	echo "$(CMD_X86_PREFIX)debug $(config)";\
	$(CMD_X86_PREFIX)debug $(config)


# Clean all build files.
.PHONY: clean
clean:
	rm -rf build


.PHONY: bell
bell:
	@printf '\a';\
	echo 'Ding!'
