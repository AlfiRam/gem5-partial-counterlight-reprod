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
tests = ["bodytrack_5m-new"]

for test in tests:
    data_gen_west_points(
        args.base_dir,
        filename=f"{test}-l1-stack-access",
        test=test,
        sets=128,
        distances=8,
        stat_name=(
            "L1 Set stack distance",
            "board.cache_hierarchy.l1caches.tags.setStackDistance",
        ),
        # include_filter=["app-dram-only"],
        title=f"{test} - L1 Stack Accesses",
        xlabel="Stack Position",
        ylabel="Access Frequency",
    )

    data_gen_west_points(
        args.base_dir,
        filename=f"{test}-l2-stack-access",
        test=test,
        sets=512,
        distances=16,
        stat_name=(
            "L2 Set stack distance",
            "board.cache_hierarchy.l2cache.tags.setStackDistance",
        ),
        # include_filter=["app-dram-only"],
        title=f"{test} - L2 Stack Accesses",
        xlabel="Stack Position",
        ylabel="Access Frequency",
    )
