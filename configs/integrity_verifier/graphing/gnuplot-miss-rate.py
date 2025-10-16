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

# testsuite11
# tests = ["spec2017-500.perlbench_r-ref", "spec2017-502.gcc_r-ref", "spec2017-549.fotonik3d_r-ref", "parsec-dedup-simlarge", "parsec-blackscholes-simlarge", "parsec-bodytrack-simlarge"]

# tests = ["micro-shortwiderandom", "micro-skippass"]

# SPECspeed
# tests = ["spec2017-600.perlbench_s-ref", "spec2017-603.bwaves_s-ref", "spec2017-605.mcf_s-ref", "spec2017-607.cactuBSSN_s-ref", "spec2017-620.omnetpp_s-ref", "spec2017-623.xalancbmk_s-ref", "spec2017-638.imagick_s-ref", "spec2017-649.fotonik3d_s-ref", "spec2017-654.roms_s-ref", "spec2017-657.xz_s-ref"]

# Just large footprint benchmarks
# tests = ["spec2017-603.bwaves_s-ref", "spec2017-654.roms_s-ref", "spec2017-657.xz_s-ref"]

# testsuite16
tests = ["spec2017-500.perlbench_r-ref"]


graphs = [
    {
        "filename": "llc-miss-rate",
        "stat": "board.cache_hierarchy.l2cache.demandMissRate::total",
        "title": "LLC Miss Rate",
        "ylabel": "Rate",
    },
    {
        "filename": "llc-miss-count",
        "stat": "board.cache_hierarchy.l2cache.demandMisses::total",
        "title": "LLC Miss Count",
        "ylabel": "Count",
    },
    {
        "filename": "metadata-miss-rate",
        "stat": "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRate",
        "title": "Metadata Cache Miss Rate",
        "ylabel": "Rate",
    },
    {
        "filename": "metadata-miss-count",
        "stat": "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMisses",
        "title": "Metadata Cache Miss Count",
        "ylabel": "Count",
    },
    {
        "filename": "metadata-miss-rate-tree-nodes",
        "stat": "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRateTypes::TreeNode",
        "title": "Tree Node Miss Rate",
        "ylabel": "Rate",
    },
    {
        "filename": "metadata-miss-rate-counter",
        "stat": "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRateTypes::Counter",
        "title": "Counter Node Miss Rate",
        "ylabel": "Rate",
    },
    {
        "filename": "metadata-miss-rate-macs",
        "stat": "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRateTypes::MAC",
        "title": "MAC Node Miss Rate",
        "ylabel": "Rate",
    },
]
for item in graphs:
    data_gen_bars_compare_runs(
        args.base_dir,
        filename=f"{item['filename']}",
        # test="",
        groups=tests,
        # groups=["parsec-" + benchmark + "-simsmall" for benchmark in parsec_benchmarks] + ["micro-shortwiderandom", "micro-skippass"],
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
                "Application on DRAM, Metadata on DRAM",
                "app-dram-integrity-dram",
            ),
            (
                "Application on DRAM, Metadata on CXL",
                "app-dram-integrity-cxl",
            ),
            (
                "Application on CXL, Metadata on DRAM",
                "app-cxl-integrity-dram",
            ),
            # (
            #     "Application on CXL, Metadata on DRAM",
            #     "app-cxl-big-integrity-dram",
            # ),
            (
                "Application on CXL, Metadata on CXL",
                "app-cxl-integrity-cxl",
            ),
            # (
            #     "Application on CXL, Metadata on CXL",
            #     "app-cxl-big-integrity-cxl-big",
            # ),
        ],
        # configurations=everything,
        stat_name=(
            item["title"],
            item["stat"],
        ),
        title=item["title"],
        xlabel="Benchmark",
        ylabel=item["ylabel"],
        perf_template="clustered-bars-integrity-only",
        # include_filter=["app"],
        exclude_filter=["PageSwapYes"],
        force_remove=args.force,
    )


data_gen_stacked(
    args.base_dir,
    filename=f"llc-miss-count-split",
    test="PageSwapNo",
    groups=tests,
    # groups=[
    #     "app-cxl-big-only",
    #     "app-cxl-big-integrity-dram",
    #     "app-cxl-big-integrity-cxl-big",
    #     # "PageSwapNo",
    #     # "PageSwapNo_CxlLat35ns",
    #     # 'PageSwapNo_CxlLat70ns',
    #     # "PageSwapYes",
    #     # "PageSwapYes_CxlLat35ns",
    #     # 'PageSwapYes_CxlLat70ns',
    # ],
    # configurations=tests,
    configurations=[
        # "app-cxl-big-only",
        # "app-cxl-big-integrity-dram",
        # "app-cxl-big-integrity-cxl-big",
        "app-dram-integrity-dram",
        "app-dram-integrity-cxl",
        "app-cxl-integrity-dram",
        "app-cxl-integrity-cxl",
    ],
    stacked_names=[
        (
            "Instruction Miss",
            "board.cache_hierarchy.l2cache.demandMisses::processor.switch.core.inst",
        ),
        (
            "Data Miss",
            "board.cache_hierarchy.l2cache.demandMisses::processor.switch.core.data",
        ),
    ],
    title="LLC Miss Type Breakdown",
    xlabel="Configuration",
    ylabel="Count",
    # different_stacked_names=True,
    force_remove=args.force,
)
