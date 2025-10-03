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

epochs = [epoch for epoch in ["25", "50", "100", "200", "400", "800"]]

data_gen_bars_compare_runs(
    args.base_dir,
    filename="runtime-swap-epoch",
    # test="",
    groups=epochs,
    columns=[
        # (
        #     "DRAM Only (No integrity)",
        #     "app-dram-only",
        # ),
        # (
        #     "CXL only (No integrity)",
        #     "app-cxl-only",
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
        (
            "Application on CXL, Integrity on CXL",
            "app-cxl-integrity-cxl",
        ),
    ],
    stat_name=(
        "Runtime",
        "simSeconds",
    ),
    title="Execution Time vs. Page Swap Epoch",
    xlabel="Page Swap Epoch (# of Requests)",
    ylabel="Time (s)",
    perf_template="linespoints",
    group_as_xaxis=True,
    # include_filter=["app"],
    exclude_filter=["PageSwapNo"],
    force_remove=args.force,
    # force_remove=False,
)


graphs = [
    {
        "filename": "swap-count",
        "stat": "board.cache_hierarchy.page_swapper.page_swapper.totalSwapCount",
        "title": "Swap Count",
        "ylabel": "Swap Count",
    },
    {
        "filename": "swap-stall-time",
        "stat": "board.cache_hierarchy.page_swapper.page_swapper.avgSwapStallTime",
        "title": "Swap Stall Time",
        "ylabel": "Time (ns)",
    },
    {
        "filename": "accesses-improved",
        "stat": "board.cache_hierarchy.page_swapper.page_swapper.accessesImproved",
        "title": "Accesses Improved",
        "ylabel": "Count",
    },
    {
        "filename": "accesses-unaffected",
        "stat": "board.cache_hierarchy.page_swapper.page_swapper.accessesUnaffected",
        "title": "Accesses Unaffected",
        "ylabel": "Count",
    },
    {
        "filename": "accesses-worsened",
        "stat": "board.cache_hierarchy.page_swapper.page_swapper.accessesWorsened",
        "title": "Accesses Worsened",
        "ylabel": "Count",
    },
    {
        "filename": "swap-page-hit-rate-dram",
        "stat": "board.cache_hierarchy.page_swapper.page_swapper.swapPageHitRateTransDram",
        "title": "DRAM Swap Page Hit Rate",
        "ylabel": "Rate",
    },
    {
        "filename": "swap-page-hit-rate-cxl",
        "stat": "board.cache_hierarchy.page_swapper.page_swapper.swapPageHitRateTransCxl",
        "title": "CXL Swap Page Hit Rate",
        "ylabel": "Rate",
    },
]
for graph in graphs:
    data_gen_bars_compare_runs(
        args.base_dir,
        filename=f"{graph['filename']}-swap-epoch",
        # test="",
        groups=epochs,
        columns=[
            # (
            #     "DRAM Only (No integrity)",
            #     "app-dram-only",
            # ),
            # (
            #     "CXL only (No integrity)",
            #     "app-cxl-only",
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
            (
                "Application on CXL, Integrity on CXL",
                "app-cxl-integrity-cxl",
            ),
        ],
        stat_name=(
            graph["title"],
            graph["stat"],
        ),
        title=f"{graph['title']} vs. Page Swap Epoch",
        xlabel="Page Swap Epoch (# of Requests)",
        ylabel=graph["ylabel"],
        perf_template="linespoints",
        group_as_xaxis=True,
        # include_filter=["app"],
        exclude_filter=["PageSwapNo"],
        force_remove=args.force,
    )
