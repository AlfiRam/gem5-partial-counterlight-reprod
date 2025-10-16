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

# sizes=[f"MetadataCacheSize{size}" for size in ["64", "128", "256", "512", "1024", "2048", "4096", "8192", "50000"]]
# sizes=[size for size in ["64", "128", "256", "512", "1024", "2048", "4096", "8192", "50000"]]
# sizes=[size for size in ["64", "128", "256", "512", "1024", "2048", "4096", "8192"]]
sizes = [size for size in ["672", "3408", "4768", "5456", "5792"]]


data_gen_bars_compare_runs(
    args.base_dir,
    filename="runtime-metadata-size",
    # test="",
    groups=sizes,
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
        (
            "Application on CXL, Metadata on CXL",
            "app-cxl-integrity-cxl",
        ),
    ],
    stat_name=(
        "Runtime",
        "simSeconds",
    ),
    title="Execution Time vs. Metadata Cache Size",
    xlabel="Metadata Cache Size",
    ylabel="Time",
    perf_template="linespoints",
    group_as_xaxis=True,
    # include_filter=["app"],
    exclude_filter=["PageSwapYes"],
    force_remove=args.force,
    # force_remove=False,
)


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
for graph in graphs:
    data_gen_bars_compare_runs(
        args.base_dir,
        filename=f"{graph['filename']}-metadata-size",
        # test="",
        groups=sizes,
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
            (
                "Application on CXL, Metadata on CXL",
                "app-cxl-integrity-cxl",
            ),
        ],
        stat_name=(
            graph["title"],
            graph["stat"],
        ),
        title=f"{graph['title']} vs. Metadata Cache Size",
        xlabel="Metadata Cache Size",
        ylabel=graph["title"],
        perf_template="linespoints",
        group_as_xaxis=True,
        # include_filter=["app"],
        exclude_filter=["PageSwapYes"],
        force_remove=args.force,
    )
