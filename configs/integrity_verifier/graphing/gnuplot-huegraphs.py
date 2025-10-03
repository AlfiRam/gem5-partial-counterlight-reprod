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


tests = [
    "parsec-" + benchmark + "-simsmall"
    for benchmark in [
        "blackscholes",
        "bodytrack",
        "dedup",
        "ferret",
        "swaptions",
    ]
]

variations = [
    {
        "filename": "llc-miss-rate",
        "secondary_stat": (
            "LLC Miss Rate",
            "board.cache_hierarchy.l2cache.demandMissRate::total",
        ),
    },
    {
        "filename": "metadata-miss-rate",
        "secondary_stat": (
            "Metadata Cache Miss Rate",
            "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRate",
        ),
    },
    {
        "filename": "metadata-miss-rate-tree-nodes",
        "secondary_stat": (
            "Tree Node Miss Rate",
            "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRateTypes::TreeNode",
        ),
    },
    {
        "filename": "metadata-miss-rate-counter",
        "secondary_stat": (
            "Counter Node Miss Rate",
            "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRateTypes::Counter",
        ),
    },
    {
        "filename": "metadata-miss-rate-macs",
        "secondary_stat": (
            "MAC Node Miss Rate",
            "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRateTypes::MAC",
        ),
    },
    {
        "filename": "runtime",
        "secondary_stat": (
            "Simulated Execution Time",
            "simSeconds",
        ),
    },
    {
        "filename": "load-store-proportion",
        "secondary_stat": (
            "Load/Store Proportion",
            lambda path: (
                extract_stat(
                    path,
                    "board.processor.switch0.core.commitStats0.numLoadInsts",
                )
                + extract_stat(
                    path,
                    "board.processor.switch0.core.commitStats0.numStoreInsts",
                )
            )
            / extract_stat(
                path, "board.processor.switch0.core.commitStats0.numInsts"
            ),
        ),
    },
    {
        "filename": "total-load-store",
        "secondary_stat": (
            "Total Loads/Stores",
            lambda path: extract_stat(
                path, "board.processor.switch0.core.commitStats0.numLoadInsts"
            )
            + extract_stat(
                path, "board.processor.switch0.core.commitStats0.numStoreInsts"
            ),
        ),
    },
    {
        "filename": "load-store-rate",
        "secondary_stat": (
            "Avg. Loads/Stores Per Second",
            lambda path: (
                extract_stat(
                    path,
                    "board.processor.switch0.core.commitStats0.numLoadInsts",
                )
                + extract_stat(
                    path,
                    "board.processor.switch0.core.commitStats0.numStoreInsts",
                )
            )
            / extract_stat(path, "simSeconds"),
        ),
    },
]
for variation in variations:
    data_gen_bars_compare_runs2(
        args.base_dir,
        filename=f"runtime-vs-{variation['filename']}",
        # test="",
        groups=tests,
        # groups=["parsec-" + benchmark + "-simsmall" for benchmark in parsec_benchmarks if benchmark not in ["facesim", "x264"]] + ["micro-shortwiderandom", "micro-skippass"],
        # groups=["parsec-" + benchmark + "-simsmall" for benchmark in parsec_benchmarks] + ["micro-shortwiderandom", "micro-skippass"],
        columns=[
            (
                "DRAM Only (No integrity)",
                "app-dram-only",
            ),
            (
                "CXL Only (No integrity)",
                "app-cxl-only",
            ),
            (
                "Application on DRAM, Integrity on DRAM",
                "app-dram-integrity-dram",
            ),
            (
                "Application on DRAM, Integrity on CXL",
                "app-dram-integrity-cxl",
            ),
            (
                "Application on CXL, Integrity on DRAM",
                "app-cxl-integrity-dram",
            ),
            (
                "Application on CXL, Integrity on CXL",
                "app-cxl-integrity-cxl",
            ),
        ],
        # configurations=everything,
        stat_name=(
            "Simulated Execution Time",
            "simSeconds",
        ),
        # stat_name=(
        #     "LLC Miss Latency",
        #     "board.cache_hierarchy.l2cache.demandAvgMissLatency::total",
        # ),
        # secondary_stat=(
        #     "LLC miss rate",
        #     "board.cache_hierarchy.l2cache.demandMissRate::total",
        # ),
        # secondary_stat=(
        #     "Metadata Cache Miss Rate",
        #     "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRate",
        # ),
        secondary_stat=variation["secondary_stat"],
        title="Execution Time",
        xlabel="Benchmark",
        ylabel="Time (s)",
        # include_filter=["app"],
        exclude_filter=["PageSwapYes"],
    )
