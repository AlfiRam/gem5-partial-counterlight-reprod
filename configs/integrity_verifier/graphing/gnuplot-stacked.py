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

# tests=["parsec-" + benchmark + "-simsmall" for benchmark in ["blackscholes", "bodytrack", "dedup", "ferret", "swaptions"]]
# tests=["parsec-" + benchmark + "-simsmall" for benchmark in parsec_benchmarks if benchmark not in ["facesim", "x264"]] + ["micro-shortwiderandom", "micro-skippass"]
tests = ["micro-shortwiderandom", "micro-skippass"]

for test in tests:
    # Stacked graphs that show proportion of requests handled,
    # either with or without page swapping
    data_gen_stacked(
        args.base_dir,
        filename=f"reqHandledTrans-{test}",
        test=test,
        groups=[
            "PageSwapNo",
            # "PageSwapNo_CxlLat35ns",
            # 'PageSwapNo_CxlLat70ns',
            "PageSwapYes",
            # "PageSwapYes_CxlLat35ns",
            # 'PageSwapYes_CxlLat70ns',
        ],
        configurations=[
            "app-dram-integrity-dram",
            "app-dram-integrity-cxl",
            "app-cxl-integrity-dram",
            "app-cxl-integrity-cxl",
        ],
        # stacked_names=[
        #     (
        #         "reqHandledDramOs",
        #         "board.cache_hierarchy.verifier.integrity_verifier.reqHandledDramOs",
        #     ),
        #     (
        #         "reqHandledDramIntegrity",
        #         "board.cache_hierarchy.verifier.integrity_verifier.reqHandledDramIntegrity",
        #     ),
        #     (
        #         "reqHandledCxlOs",
        #         "board.cache_hierarchy.verifier.integrity_verifier.reqHandledCxlOs",
        #     ),
        #     (
        #         "reqHandledCxlIntegrity",
        #         "board.cache_hierarchy.verifier.integrity_verifier.reqHandledCxlIntegrity",
        #     ),
        # ],
        # stacked_names=[
        #     (
        #         "bytesHandledDramOs",
        #         "board.cache_hierarchy.verifier.integrity_verifier.bytesHandledDramOs",
        #     ),
        #     (
        #         "bytesHandledDramIntegrity",
        #         "board.cache_hierarchy.verifier.integrity_verifier.bytesHandledDramIntegrity",
        #     ),
        #     (
        #         "bytesHandledCxlOs",
        #         "board.cache_hierarchy.verifier.integrity_verifier.bytesHandledCxlOs",
        #     ),
        #     (
        #         "bytesHandledCxlIntegrity",
        #         "board.cache_hierarchy.verifier.integrity_verifier.bytesHandledCxlIntegrity",
        #     ),
        # ],
        stacked_names=[
            [
                (
                    "reqHandledDramOs",
                    "board.cache_hierarchy.verifier.integrity_verifier.reqHandledDramOs",
                ),
                (
                    "reqHandledDramIntegrity",
                    "board.cache_hierarchy.verifier.integrity_verifier.reqHandledDramIntegrity",
                ),
                (
                    "reqHandledCxlOs",
                    "board.cache_hierarchy.verifier.integrity_verifier.reqHandledCxlOs",
                ),
                (
                    "reqHandledCxlIntegrity",
                    "board.cache_hierarchy.verifier.integrity_verifier.reqHandledCxlIntegrity",
                ),
            ],
            [
                (
                    "reqHandledTransDramOs",
                    "board.cache_hierarchy.verifier.integrity_verifier.reqHandledTransDramOs",
                ),
                (
                    "reqHandledTransDramIntegrity",
                    "board.cache_hierarchy.verifier.integrity_verifier.reqHandledTransDramIntegrity",
                ),
                (
                    "reqHandledTransCxlOs",
                    "board.cache_hierarchy.verifier.integrity_verifier.reqHandledTransCxlOs",
                ),
                (
                    "reqHandledTransCxlIntegrity",
                    "board.cache_hierarchy.verifier.integrity_verifier.reqHandledTransCxlIntegrity",
                ),
            ],
        ],
        title="Requests Handled",
        xlabel="Configuration",
        ylabel="Number of Requests (Count)",
        different_stacked_names=True,
    )
