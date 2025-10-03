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
# tests = ["micro-shortwiderandom", "micro-skippass"]
# tests = ["spec2017-500.perlbench_r-ref", "spec2017-502.gcc_r-ref", "spec2017-549.fotonik3d_r-ref", "parsec-dedup-simlarge", "parsec-blackscholes-simlarge", "parsec-bodytrack-simlarge"]
# tests = ["spec2017-500.perlbench_r-ref", "spec2017-549.fotonik3d_r-ref"]

# Just large footprint benchmarks
# tests = ["spec2017-603.bwaves_s-ref", "spec2017-654.roms_s-ref", "spec2017-657.xz_s-ref"]

# testsuite16
tests = ["spec2017-500.perlbench_r-ref"]

graphs = [
    {
        "filename": "hosttime",
        "stat": "hostSeconds",
        "title": "Wall Clock Time",
        "ylabel": "Time (s)",
    },
    {
        "filename": "runtime",
        "stat": "simSeconds",
        "title": "Execution Time",
        "ylabel": "Time (s)",
    },
]

for graph in graphs:
    data_gen_bars_compare_runs(
        args.base_dir,
        filename=graph["filename"],
        # test="",
        groups=tests,
        columns=[
            # (
            #     "DRAM Only (No integrity)",
            #     "app-dram-only",
            # ),
            # (
            #     "CXL only (No integrity)",
            #     "app-cxl-only",
            # ),
            # (
            #     "CXL Only (No integrity)",
            #     "app-cxl-big-only",
            # ),
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
            # (
            #     "Application on CXL, Integrity on DRAM",
            #     "app-cxl-big-integrity-dram",
            # ),
            (
                "Application on CXL, Integrity on CXL",
                "app-cxl-integrity-cxl",
            ),
            # (
            #     "Application on CXL, Integrity on CXL",
            #     "app-cxl-big-integrity-cxl-big",
            # ),
        ],
        # configurations=everything,
        stat_name=(
            graph["title"],
            graph["stat"],
        ),
        title=graph["title"],
        xlabel="Benchmark",
        ylabel=graph["ylabel"],
        perf_template="clustered-bars-integrity-only",
        # include_filter=["app"],
        exclude_filter=["PageSwapYes"],
        force_remove=args.force,
    )
