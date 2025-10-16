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

# testsuite11
# tests = ["spec2017-500.perlbench_r-ref", "spec2017-502.gcc_r-ref", "spec2017-549.fotonik3d_r-ref", "parsec-dedup-simlarge", "parsec-blackscholes-simlarge", "parsec-bodytrack-simlarge"]

# tests = ["spec2017-500.perlbench_r-ref", "spec2017-549.fotonik3d_r-ref"]

# Just large footprint benchmarks
tests = [
    "spec2017-603.bwaves_s-ref",
    "spec2017-654.roms_s-ref",
    "spec2017-657.xz_s-ref",
]


data_gen_stacked(
    args.base_dir,
    filename=f"swapped-pages",
    test="PageSwapYes",
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
        "app-cxl-big-only",
        "app-cxl-big-integrity-dram",
        "app-cxl-big-integrity-cxl-big",
        # "app-dram-integrity-dram",
        # "app-dram-integrity-cxl",
        # "app-cxl-integrity-dram",
        # "app-cxl-integrity-cxl",
    ],
    stacked_names=[
        (
            "DRAM, Application",
            "board.cache_hierarchy.page_swapper.page_swapper.pagesSwappedDramOs",
        ),
        (
            "DRAM, Integrity",
            "board.cache_hierarchy.page_swapper.page_swapper.pagesSwappedDramIntegrity",
        ),
        (
            "CXL, Application",
            "board.cache_hierarchy.page_swapper.page_swapper.pagesSwappedCxlOs",
        ),
        (
            "CXL, Integrity",
            "board.cache_hierarchy.page_swapper.page_swapper.pagesSwappedCxlIntegrity",
        ),
    ],
    title="Pages Swapped",
    xlabel="",
    ylabel="Pages",
    # different_stacked_names=True,
    force_remove=args.force,
)


# data_gen_bars_compare_runs(
#     args.base_dir,
#     filename="req-improved",
#     # test="",
#     groups=tests,
#     columns=[
#         (
#             "DRAM Only (No integrity)",
#             "app-dram-only",
#         ),
#         (
#             "CXL Only (No integrity)",
#             "app-cxl-only",
#         ),
#         # (
#         #     "CXL Only (No integrity)",
#         #     "app-cxl-big-only",
#         # ),
#         (
#             "Application on DRAM, Metadata on DRAM (No Page Swap)",
#             "app-dram-integrity-dram.*PageSwapNo",
#         ),
#         ## (
#         ##     "Application on DRAM, Metadata on DRAM (Page Swap)",
#         ##     "app-dram-integrity-dram.*PageSwapYes",
#         ## ),
#         (
#             "Application on DRAM, Metadata on CXL (No Page Swap)",
#             "app-dram-integrity-cxl.*PageSwapNo",
#         ),
#         (
#             "Application on DRAM, Metadata on CXL (Page Swap)",
#             "app-dram-integrity-cxl.*PageSwapYes",
#         ),
#         (
#             "Application on CXL, Metadata on DRAM (No Page Swap)",
#             "app-cxl-integrity-dram.*PageSwapNo",
#         ),
#         # (
#         #     "Application on CXL, Metadata on DRAM (No Page Swap)",
#         #     "app-cxl-big-integrity-dram.*PageSwapNo",
#         # ),
#         (
#             "Application on CXL, Metadata on DRAM (Page Swap)",
#             "app-cxl-integrity-dram.*PageSwapYes",
#         ),
#         # (
#         #     "Application on CXL, Metadata on DRAM (Page Swap)",
#         #     "app-cxl-big-integrity-dram.*PageSwapYes",
#         # ),
#         (
#             "Application on CXL, Metadata on CXL (No Page Swap)",
#             "app-cxl-integrity-cxl.*PageSwapNo",
#         ),
#         # (
#         #     "Application on CXL, Metadata on CXL (No Page Swap)",
#         #     "app-cxl-big-integrity-cxl-big.*PageSwapNo",
#         # ),
#         (
#             "Application on CXL, Metadata on CXL (Page Swap)",
#             "app-cxl-integrity-cxl.*PageSwapYes",
#         ),
#         # (
#         #     "Application on CXL, Metadata on CXL (Page Swap)",
#         #     "app-cxl-big-integrity-cxl-big.*PageSwapYes",
#         # ),
#     ],
#     # configurations=everything,
#     stat_name=(
#         "runtime",
#         "simSeconds",
#     ),
#     # secondary_stat=(
#     #     "LLC miss rate",
#     #     "board.cache_hierarchy.l2cache.demandMissRate::total",
#     # ),
#     # secondary_stat=(
#     #     "Metadata Cache Miss Rate",
#     #     "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRate",
#     # ),
#     title="Execution Time",
#     xlabel="Benchmark",
#     ylabel="Time",
#     # include_filter=["app"],
#     # exclude_filter=["PageSwapYes"],
#     use_regex=True,
#     perf_template="clustered-bars-swapping",
# )
