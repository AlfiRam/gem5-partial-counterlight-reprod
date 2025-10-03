#!/usr/bin/env python3

import argparse
from pathlib import Path

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

# Get everything run
tests = [d.name for d in Path(args.base_dir).iterdir() if d.is_dir()]


data_gen_coordinates(
    args.base_dir,
    filename="hosttime-vs-insts",
    tests=tests,
    x_stat="simInsts",
    y_stat="hostSeconds",
    title="Total Wall Clock Time vs. Instructions Retired",
    xlabel="Instructions",
    ylabel="Wall Clock Time (s)",
)

data_gen_simple(
    args.base_dir,
    filename="instrate",
    tests=tests,
    stat="hostInstRate",
    title="Host Instruction Simulation Rates",
    xlabel="",
    ylabel="Instructions per Second",
)

data_gen_simple(
    args.base_dir,
    filename="tickrate",
    tests=tests,
    stat="hostTickRate",
    title="Host Tick Simulation Rates",
    xlabel="",
    ylabel="Ticks per Second",
)
