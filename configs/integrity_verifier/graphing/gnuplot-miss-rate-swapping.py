#!/usr/bin/env python3

import argparse

from export_data_gnuplot import *

# Argument parsing.
parser = argparse.ArgumentParser(
    description="Export many gem5 runs into data files for gnuplot."
)
parser = add_arguments(parser)
args = parser.parse_args()


# Generate data

# tests=["parsec-" + benchmark + "-simsmall" for benchmark in parsec_benchmarks if benchmark not in ["facesim", "x264"]] + ["micro-shortwiderandom", "micro-skippass"]
# tests=["parsec-" + benchmark + "-simsmall" for benchmark in ["blackscholes", "bodytrack", "dedup", "ferret", "swaptions"]]
# tests = ["spec2017-500.perlbench_r-ref", "spec2017-502.gcc_r-ref", "spec2017-549.fotonik3d_r-ref", "parsec-dedup-simlarge", "parsec-blackscholes-simlarge", "parsec-bodytrack-simlarge"]
# tests = ["micro-shortwiderandom", "micro-skippass"]

# testsuite16
tests = ["spec2017-500.perlbench_r-ref"]


data_gen_bars_compare_runs_multiple_stats(
    args.base_dir,
    filename="llc-metadata-miss-rate",
    # test="",
    groups=tests,
    columns=[
        # (
        #     "DRAM Only (No integrity)",
        #     "app-dram-only",
        # ),
        # (
        #     "CXL Only (No integrity)",
        #     "app-cxl-only",
        # ),
        (
            "Application on DRAM, Metadata on DRAM (No Page Swap)",
            "app-dram-integrity-dram.*PageSwapNo",
        ),
        # (
        #     "Application on DRAM, Metadata on DRAM (Page Swap)",
        #     "app-dram-integrity-dram.*PageSwapYes",
        # ),
        (
            "Application on DRAM, Metadata on CXL (No Page Swap)",
            "app-dram-integrity-cxl.*PageSwapNo",
        ),
        (
            "Application on DRAM, Metadata on CXL (Page Swap)",
            "app-dram-integrity-cxl.*PageSwapYes",
        ),
        (
            "Application on CXL, Metadata on DRAM (No Page Swap)",
            "app-cxl-integrity-dram.*PageSwapNo",
        ),
        (
            "Application on CXL, Metadata on DRAM (Page Swap)",
            "app-cxl-integrity-dram.*PageSwapYes",
        ),
        (
            "Application on CXL, Metadata on CXL (No Page Swap)",
            "app-cxl-integrity-cxl.*PageSwapNo",
        ),
        (
            "Application on CXL, Metadata on CXL (Page Swap)",
            "app-cxl-integrity-cxl.*PageSwapYes",
        ),
    ],
    # configurations=everything,
    stat_names=[
        (
            "LLC Miss Rate",
            "board.cache_hierarchy.l2cache.demandMissRate::total",
        ),
        (
            "Metadata Cache Miss Rate",
            "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRate",
        ),
    ],
    title="LLC and Metadata Miss Rates",
    xlabel="Benchmark",
    ylabel="Miss Rate",
    # include_filter=["app"],
    # exclude_filter=["PageSwapYes"],
    exclude_filter=[
        "SwapEpoch50",
        "SwapEpoch100",
        "SwapEpoch200",
        "SwapEpoch400",
        "SwapEpoch800",
    ],
    use_regex=True,
    # perf_template="clustered-bars-swapping-double",
    perf_template="clustered-bars-swapping-double-integrity-only",
    force_remove=args.force,
)
