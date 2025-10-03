#!/usr/bin/env python3

import argparse
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from decimal import Decimal

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def extract_int(folder_path, stat):
    """Extract stat from stats.txt in the given folder."""
    stats_file = os.path.join(folder_path, "stats.txt")
    stat_val = None

    assert os.path.isfile(stats_file)

    with open(stats_file) as file:
        for line in file:
            if stat in line:
                stat_val = int(line.split()[1])  # Extract the value
                break

    assert stat_val is not None
    # Default value
    # if stat_val is None:
    #     stat_val = 0

    return stat_val


def extract_float(folder_path, stat):
    """Extract stat from stats.txt in the given folder."""
    stats_file = os.path.join(folder_path, "stats.txt")
    stat_val = None

    assert os.path.isfile(stats_file)

    with open(stats_file) as file:
        for line in file:
            if stat in line:
                stat_val = float(line.split()[1])  # Extract the value
                break

    assert stat_val is not None
    # # Default value
    # if stat_val is None:
    #     stat_val = 0.0

    return stat_val


def add_arguments(parser):
    parser.add_argument(
        "--base-dir",
        type=str,
        required=True,
        help="Directory with all gem5 runs.",
    )
    # parser.add_argument(
    #     "--force",
    #     action="store_true",
    #     required=False,
    #     help="Replace files if they already exist."
    # )

    return parser


def main(base_directory):
    # stats = os.path.join(base_directory, "stats.txt")
    stats = base_directory
    reuse_count = 8
    caches = [
        # L1
        {
            "name": "board.cache_hierarchy.l1caches",
            "sets": 128,
            "ways": 8,
        },
        # L2
        {
            "name": "board.cache_hierarchy.l2cache",
            "sets": 512,
            "ways": 16,
        },
    ]
    with open(os.path.join(base_directory, "west-export.txt"), "w") as file:
        file.write(f"{len(caches)}\n")
        for cache in caches:
            # Initialize arrays
            ssd_array = []
            sr_array = []
            wc_array = []
            rc_array = []
            for _ in range(cache["sets"]):
                array = []
                for _ in range(cache["ways"] + 1):
                    array.append(0.0)
                ssd_array.append(array)

            for _ in range(reuse_count + 1):
                sr_array.append(0.0)

            for _ in range(cache["sets"]):
                array = []
                for _ in range(cache["ways"] + 1):
                    array.append(0.0)
                wc_array.append(array)

            for _ in range(cache["sets"]):
                array = []
                for _ in range(cache["ways"] + 1):
                    array.append(0.0)
                rc_array.append(array)

            # Read data from file
            stats_file = os.path.join(base_directory, "stats.txt")
            stat_val = None
            assert os.path.isfile(stats_file)
            with open(stats_file) as stats_f:
                for line in stats_f:
                    if f"{cache['name']}.tags.setStackDistance_" in line:
                        temp = (
                            line.split()[0]
                            .split("tags.setStackDistance_")[1]
                            .split("::")
                        )
                        set = int(temp[0])
                        way = int(temp[1])
                        ssd_array[set][way] = int(line.split()[1])
                    elif f"{cache['name']}.tags.setReuse::" in line:
                        temp = line.split()[0].split("tags.setReuse::")
                        i = int(temp[1])
                        sr_array[i] = int(line.split()[1])
                    elif f"{cache['name']}.tags.writeCount_" in line:
                        temp = (
                            line.split()[0]
                            .split("tags.writeCount_")[1]
                            .split("::")
                        )
                        set = int(temp[0])
                        way = int(temp[1])
                        wc_array[set][way] = int(line.split()[1])
                    elif f"{cache['name']}.tags.readCount_" in line:
                        temp = (
                            line.split()[0]
                            .split("tags.readCount_")[1]
                            .split("::")
                        )
                        set = int(temp[0])
                        way = int(temp[1])
                        rc_array[set][way] = int(line.split()[1])
                    else:
                        # Ignore other lines
                        pass

            file.write(f"{cache['sets']}\n")
            file.write(f"{cache['ways']}\n")
            # accesses = extract_stat(stats, cache['name'] + '')
            accesses = sum(sr_array)
            file.write(f"{accesses}\n")

            # SSD: Set Stack Distance
            for set in range(cache["sets"]):
                for way in range(cache["ways"] + 1):
                    # .tags.setStackDistance_0::0
                    stat = (
                        f"{cache['name']}.tags.setStackDistance_{set}::{way}"
                    )
                    print(stat)
                    # ssd = extract_int(stats, f"{cache['name']}.tags.setStackDistance_{set}::{way}")
                    ssd = Decimal(
                        ssd_array[set][way] / sum(ssd_array[set])
                    ).normalize()

                    file.write(f"{ssd}")

                    if way < cache["ways"]:
                        file.write(" ")
                file.write("\n")

            # SR: Set Reuse
            for i in range(reuse_count + 1):
                # .tags.setReuse::0
                stat = f"{cache['name']}.tags.setReuse::{i}"
                print(stat)
                # sr = extract_int(stats, f"{cache['name']}.tags.setReuse::{i}")
                sr = Decimal(sr_array[i] / sum(sr_array)).normalize()

                file.write(f"{sr}")

                if i < reuse_count:
                    file.write(" ")
            file.write("\n")

            # WF: Write Fraction
            for set in range(cache["sets"]):
                for way in range(cache["ways"] + 1):
                    # .tags.writeCount_0::0
                    stat = f"{cache['name']}.tags.writeCount_{set}::{way}"
                    print(stat)
                    # wc = extract_int(stats, f"{cache['name']}.tags.writeCount_{set}::{way}")
                    wc = wc_array[set][way]

                    stat = f"{cache['name']}.tags.readCount_{set}::{way}"
                    print(stat)
                    # rc = extract_int(stats, f"{cache['name']}.tags.readCount_{set}::{way}")
                    rc = rc_array[set][way]

                    if wc + rc == 0:
                        wf = Decimal(0).normalize()
                    else:
                        wf = Decimal(wc / (wc + rc)).normalize()
                    file.write(f"{wf}")

                    if way < cache["ways"]:
                        file.write(" ")
                file.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export WEST-style profiling data."
    )
    parser = add_arguments(parser)
    args = parser.parse_args()

    # base_directory = (
    #     "./output/testsuite7"  # Change this to your base directory
    # )
    base_directory = args.base_dir
    main(base_directory)
