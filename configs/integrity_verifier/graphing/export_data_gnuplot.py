#!/usr/bin/env python3

import argparse
import os
import re
import shutil
import subprocess
from collections.abc import Callable

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

force_remove = False

parsec_benchmarks = [
    "blackscholes",
    "bodytrack",
    "canneal",
    "dedup",
    "facesim",
    "ferret",
    "fluidanimate",
    "freqmine",
    "raytrace",
    "streamcluster",
    "swaptions",
    "vips",
    "x264",
]


def extract_stat(folder_path, stat):
    """Extract stat from stats.txt in the given folder."""
    stats_file = os.path.join(folder_path, "stats.txt")
    stat_val = None

    if os.path.isfile(stats_file):
        with open(stats_file) as file:
            for line in file:
                if stat in line:
                    stat_val = float(line.split()[1])  # Extract the value
                    break

    # Default value
    if stat_val is None:
        stat_val = 0.0

    return stat_val


# Generates .dat files that can be used to graph with gnuplot. (Intended for stacked bar graphs.)
def data_gen_stacked(
    base_directory,
    filename,
    test,
    groups,
    configurations,
    stacked_names,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    perf_template: str = "clustered-stacked-bars",
    different_stacked_names: bool = False,
    force_remove: bool = False,
):
    # Need:
    #  - List of groups (for clustering bars)
    #  - List of tests/configurations being compared (entries within each cluster)
    #  - List of stacked names (for stacked data)

    # test acts as a filter of what data to use
    # each group is a cluster of bars
    # each configuration goes within a cluster
    # each stacked_name is part of a single bar

    # Create placeholder group label if there are no groups
    if len(groups) == 0:
        groups = ["__PLACEHOLDER__"]

    # Generate each group
    for i, group in enumerate(groups):
        # Do not use a group name in the data file if there are no groups
        if len(groups) == 1 and group == "__PLACEHOLDER__":
            data_file_name = filename + ".dat"
        else:
            data_file_name = filename + "-" + group + ".dat"

        if not force_remove and os.path.isfile(
            os.path.join(base_directory, data_file_name)
        ):
            print(f"{data_file_name} already exists. Skipping.")
            return

        with open(os.path.join(base_directory, data_file_name), "w") as file:
            # Generate first row with column headings.
            if different_stacked_names:
                file.write(
                    f"Group Configuration {' '.join(['"' + name[0] + '"' for name in stacked_names[i]])}\n"
                )
            else:
                file.write(
                    f"Group Configuration {' '.join(['"' + name[0] + '"' for name in stacked_names])}\n"
                )

            # Each row in the group
            for configuration in configurations:
                # Find the test run with the keywords
                def find_folder(base_directory, names):
                    for folder_name in os.listdir(base_directory):
                        found = True
                        for name in names:
                            if name not in folder_name:
                                # This folder does not have all the keywords
                                found = False
                                break

                        if not found:
                            continue
                        # We found a folder with all the keywords to look for
                        return folder_name
                    return None

                folder_name = find_folder(
                    base_directory, [configuration, group, test]
                )
                if folder_name is None:
                    # Skip this data, there is no matching test result
                    continue

                folder_path = os.path.join(base_directory, folder_name)

                file.write(f"{group} {configuration} ")

                # Each column
                if different_stacked_names:
                    used_stats = stacked_names[i]
                else:
                    used_stats = stacked_names
                for _, stat_name in used_stats:
                    value = extract_stat(folder_path, stat_name)
                    if value is None:
                        value = 0.0
                    file.write(f" {value}")

                file.write("\n")

        print(f"Exported {data_file_name}")

    # Do not use a group name in the data file if there are no groups
    # if len(groups) == 1 and group == "__PLACEHOLDER__":
    #     perf_file_name = filename + ".perf"
    # else:
    #     perf_file_name = filename + "-" + group + ".perf"

    perf_file_name = filename + ".perf"

    # Copy the template file to a new file
    shutil.copy(
        os.path.join(
            "configs/integrity_verifier/graphing/gnuplot-templates/",
            perf_template + ".perf",
        ),
        os.path.join(base_directory, perf_file_name),
    )

    with open(os.path.join(base_directory, perf_file_name), "a") as file:
        file.write("\n\n")
        file.write(f'set title "{title}"\n')
        file.write(f'set xlabel "{xlabel}"\n')
        file.write(f'set ylabel "{ylabel}"\n')
        file.write("\n\n")
        file.write(
            f'set output "{os.path.join(base_directory, filename + ".png")}"\n'
        )

        file.write("plot ")
        for i, group in enumerate(groups):
            file.write(f"newhistogram '{group}', ")

            # Do not use a group name in the data file if there are no groups
            if len(groups) == 1 and group == "__PLACEHOLDER__":
                data_file_name = filename + ".dat"
            else:
                data_file_name = filename + "-" + group + ".dat"

            file.write(
                f"'{os.path.join(base_directory, data_file_name)}' using "
            )

            if different_stacked_names:
                used_stats = stacked_names[i]
            else:
                used_stats = stacked_names

            if i == 0:
                for j, stat in enumerate(used_stats):
                    if j == 0:
                        file.write(f"{j + 3}:xtic(2) t col ls {j + 1}")
                    else:
                        file.write(f"'' u {j + 3} ti col ls {j + 1}")

                    if j < (len(used_stats) - 1):
                        file.write(", \\\n")
            else:
                for j, stat in enumerate(used_stats):
                    if j == 0:
                        file.write(f"{j + 3}:xtic(2) notitle ls {j + 1}")
                    else:
                        file.write(f"'' u {j + 3} notitle ls {j + 1}")

                    if j < (len(used_stats) - 1):
                        file.write(", \\\n")

            if i < (len(groups) - 1):
                file.write(", \\\n")

    print(f"Exported {perf_file_name}")

    # Run gnuplot
    subprocess.run(["gnuplot", os.path.join(base_directory, perf_file_name)])


# Generates .dat files that can be used to graph with gnuplot. (Intended for bar graphs.)
def data_gen_bars(
    base_directory,
    filename,
    test,
    # groups,
    configurations,
    stat_names,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    perf_template: str = "clustered-bars",
    include_filter: list[str] = [],
    exclude_filter: list[str] = [],
    force_remove: bool = False,
):
    # Need:
    #  - List of groups (for clustering bars)
    #  - List of tests/configurations being compared (entries within each cluster)
    #  - List of stat names (for stacked data)

    # test acts as a filter of what data to use
    # configurations = one bar per configuration
    # each stat_name is grouped per configuration

    data_file_name = filename + ".dat"

    if not force_remove and os.path.isfile(
        os.path.join(base_directory, data_file_name)
    ):
        print(f"{data_file_name} already exists. Skipping.")
        return

    with open(os.path.join(base_directory, data_file_name), "w") as file:
        # Generate first row with column headings.
        file.write(
            f"Configuration {' '.join(['"' + name[0] + '"' for name in stat_names])}\n"
        )

        # Each row in the group
        for configuration in configurations:
            # Find the test run with the keywords
            def find_folder(
                base_directory, names, exclude_names: list[str] = []
            ):
                for folder_name in os.listdir(base_directory):
                    found = True
                    for name in names:
                        if name not in folder_name:
                            # This folder does not have all the keywords
                            found = False
                            break

                    for name in exclude_names:
                        if name in folder_name:
                            # This folder contains keywords that are excluded
                            found = False
                            break

                    if not found:
                        continue
                    # We found a folder with all the keywords to look for
                    return folder_name
                return None

            folder_name = find_folder(
                base_directory,
                [configuration, test] + include_filter,
                exclude_names=exclude_filter,
            )
            if folder_name is None:
                # Skip this data, there is no matching test result
                continue

            folder_path = os.path.join(base_directory, folder_name)

            file.write(f"{configuration} ")

            # Each column
            for _, stat_name in stat_names:
                value = extract_stat(folder_path, stat_name)
                if value is None:
                    value = 0.0
                file.write(f" {value}")

            file.write("\n")

    print(f"Exported {data_file_name}")

    perf_file_name = filename + ".perf"

    # Try to remove target .perf file if it already exists
    try:
        os.remove(os.path.join(base_directory, perf_file_name))
    except OSError:
        pass

    # Copy the template file to a new file
    shutil.copy(
        os.path.join(
            "configs/integrity_verifier/graphing/gnuplot-templates/",
            perf_template + ".perf",
        ),
        os.path.join(base_directory, perf_file_name),
    )

    with open(os.path.join(base_directory, perf_file_name), "a") as file:
        file.write("\n\n")
        file.write(f'set title "{title}"\n')
        file.write(f'set xlabel "{xlabel}"\n')
        file.write(f'set ylabel "{ylabel}"\n')
        file.write("\n\n")
        file.write(
            f'set output "{os.path.join(base_directory, filename + ".png")}"\n'
        )

        file.write("plot newhistogram '', ")
        file.write(f"'{os.path.join(base_directory, data_file_name)}' using ")
        for i, stat in enumerate(stat_names):
            if i == 0:
                file.write(f"{i + 2}:xtic(1) t col ls {i + 1}")
            else:
                file.write(f"'' u {i + 2} ti col ls {i + 1}")

            if i < (len(stat_names) - 1):
                file.write(", ")

    print(f"Exported {perf_file_name}")

    # Run gnuplot
    subprocess.run(["gnuplot", os.path.join(base_directory, perf_file_name)])


# Generates .dat files that can be used to graph with gnuplot. (Intended for bar graphs.)
# This is a variation that allows multiple simulations on a single row. This grabs
# the same one piece of data from each run.
# The structure is like the following:
# Group     Column1 Column2 Column3 Column4
# Group1    xxx     xxx     xxx     xxx
# Group2    xxx     xxx     xxx     xxx
# ...
#
# Where each column name and group name are keywords in a run.
def data_gen_bars_compare_runs(
    base_directory,
    filename,  # output filename
    # test,
    groups,  # each row
    columns: list[
        tuple[str, str]
    ],  # List of tuples: (human readable name, codename used in file names)
    stat_name: tuple[str, str],  # Human readable name, codename used in stats
    secondary_stat: tuple[
        str, str
    ] = None,  # Human readable name, codename used in stats
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    perf_template: str = "clustered-bars",
    include_filter: list[str] = [],
    exclude_filter: list[str] = [],
    use_regex: bool = False,
    # Whether to use the group name (first column) directly as the x-axis. Data must be properly-formatted.
    group_as_xaxis: bool = False,
    force_remove: bool = False,
):
    data_file_name = filename + ".dat"

    if not force_remove and os.path.isfile(
        os.path.join(base_directory, data_file_name)
    ):
        print(f"{data_file_name} already exists. Skipping.")
        return

    with open(os.path.join(base_directory, data_file_name), "w") as file:
        # Generate first row with column headings.
        if secondary_stat is None:
            # Use standard column headings.
            file.write(
                f"Group {' '.join(['"' + column[0] + '"' for column in columns])}\n"
            )
        else:
            # Alternate headings to add the secondary stat.
            file.write(
                f"Group {' '.join(['"' + column[0] + '" "' + column[0] + ' - ' + secondary_stat[0] + '"' for column in columns])}\n"
            )

        # Each row (group)
        for group in groups:
            # Find the test run with the keywords
            def find_folder(
                base_directory,
                names,
                exclude_names: list[str] = [],
                regex="",
                use_regex: bool = False,
            ):
                for folder_name in os.listdir(base_directory):
                    found = True

                    # This folder does not match the regex
                    if use_regex and not re.search(regex, folder_name):
                        found = False

                    for name in names:
                        if name not in folder_name:
                            # This folder does not have all the keywords
                            found = False
                            break

                    for name in exclude_names:
                        if name in folder_name:
                            # This folder contains keywords that are excluded
                            found = False
                            break

                    if not found:
                        continue
                    # We found a folder with all the keywords to look for
                    return folder_name
                return None

            file.write(f"{group} ")

            # Each column
            for column in columns:
                if use_regex:
                    folder_name = find_folder(
                        base_directory,
                        [group] + include_filter,
                        exclude_names=exclude_filter,
                        regex=column[1],
                        use_regex=True,
                    )
                else:
                    folder_name = find_folder(
                        base_directory,
                        [group, column[1]] + include_filter,
                        exclude_names=exclude_filter,
                    )
                if folder_name is None:
                    # Skip this data, there is no matching test result
                    continue

                print(folder_name)

                folder_path = os.path.join(base_directory, folder_name)

                value = extract_stat(folder_path, stat_name[1])
                if value is None:
                    value = 0.0
                file.write(f" {value}")

                if secondary_stat is not None:
                    secondary_value = extract_stat(
                        folder_path, secondary_stat[1]
                    )
                    if secondary_value is None:
                        secondary_value = 0.0
                    file.write(f" {secondary_value}")

            file.write("\n")

    print(f"Exported {data_file_name}")

    perf_file_name = filename + ".perf"

    # Try to remove target .perf file if it already exists
    try:
        os.remove(os.path.join(base_directory, perf_file_name))
    except OSError:
        pass

    # Copy the template file to a new file
    shutil.copy(
        os.path.join(
            "configs/integrity_verifier/graphing/gnuplot-templates/",
            perf_template + ".perf",
        ),
        os.path.join(base_directory, perf_file_name),
    )

    with open(os.path.join(base_directory, perf_file_name), "a") as file:
        file.write("\n\n")
        file.write(f'set title "{title}"\n')
        file.write(f'set xlabel "{xlabel}"\n')
        file.write(f'set ylabel "{ylabel}"\n')
        if secondary_stat is not None:
            file.write(f'set cblabel "{secondary_stat[0]}"\n')
        file.write("\n\n")
        file.write(
            f'set output "{os.path.join(base_directory, filename + ".png")}"\n'
        )

        file.write("plot newhistogram '', ")
        file.write(f"'{os.path.join(base_directory, data_file_name)}' using ")
        for i, column in enumerate(columns):
            if secondary_stat is None:
                if group_as_xaxis:
                    if i == 0:
                        file.write(f'1:{i + 2} t "{column[0]}" ls {i + 1}')
                    else:
                        file.write(
                            f"'' u 1:{i + 2} ti \"{column[0]}\" ls {i + 1}"
                        )
                else:
                    if i == 0:
                        file.write(
                            f'{i + 2}:xtic(1) t "{column[0]}" ls {i + 1}'
                        )
                    else:
                        file.write(
                            f"'' u {i + 2} ti \"{column[0]}\" ls {i + 1}"
                        )
            else:
                # secondary_stat is not None
                if i == 0:
                    file.write(
                        f'($0):{(2*i) + 2}:{(2*i) + 3}:xtic(1) t "{column[0]}" ls {i + 1}'
                    )
                else:
                    file.write(
                        f"'' u ($0):{(2*i) + 2}:{(2*i) + 3} ti \"{column[0]}\" ls {i + 1}"
                    )

            if i < (len(columns) - 1):
                file.write(", \\\n")

    print(f"Exported {perf_file_name}")

    # Run gnuplot
    subprocess.run(["gnuplot", os.path.join(base_directory, perf_file_name)])


# Generates .dat files that can be used to graph with gnuplot. (Intended for bar graphs.)
# This is a variation that allows multiple simulations on a single row. This grabs
# the same multiple pieces of data from each run.
# The structure is like the following:
# Group     Column1_1 Column1_2 Column2_1 Column2_2 Column3_1 ...
# Group1    xxx       xxx       xxx       xxx       xxx
# Group2    xxx       xxx       xxx       xxx       xxx
# ...
#
# Where each column name and group name are keywords in a run.
def data_gen_bars_compare_runs_multiple_stats(
    base_directory,
    filename,  # output filename
    # test,
    groups,  # each row
    columns: list[
        tuple[str, str]
    ],  # List of tuples: (human readable name, codename used in file names)
    stat_names: list[
        tuple[str, str]
    ],  # List of tuples: (Human readable name, codename used in stats)
    # secondary_stat: tuple[str, str] = None, # Human readable name, codename used in stats
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    perf_template: str = "clustered-bars",
    include_filter: list[str] = [],
    exclude_filter: list[str] = [],
    # Whether to use the group name (first column) directly as the x-axis. Data must be properly-formatted.
    group_as_xaxis: bool = False,
    use_regex: bool = False,
    force_remove: bool = False,
):
    data_file_name = filename + ".dat"

    if not force_remove and os.path.isfile(
        os.path.join(base_directory, data_file_name)
    ):
        print(f"{data_file_name} already exists. Skipping.")
        return

    with open(os.path.join(base_directory, data_file_name), "w") as file:
        # Generate first row with column headings.
        file.write("Group ")
        for column in columns:
            for stat, _ in stat_names:
                file.write(f'"{column[0]}, {stat}"')
        file.write("\n")

        # Each row (group)
        for group in groups:
            # Find the test run with the keywords
            def find_folder(
                base_directory,
                names,
                exclude_names: list[str] = [],
                regex="",
                use_regex: bool = False,
            ):
                for folder_name in os.listdir(base_directory):
                    found = True

                    # This folder does not match the regex
                    if use_regex and not re.search(regex, folder_name):
                        found = False

                    for name in names:
                        if name not in folder_name:
                            # This folder does not have all the keywords
                            found = False
                            break

                    for name in exclude_names:
                        if name in folder_name:
                            # This folder contains keywords that are excluded
                            found = False
                            break

                    if not found:
                        continue
                    # We found a folder with all the keywords to look for
                    return folder_name
                return None

            file.write(f"{group} ")

            # Each column
            for column in columns:
                if use_regex:
                    folder_name = find_folder(
                        base_directory,
                        [group] + include_filter,
                        exclude_names=exclude_filter,
                        regex=column[1],
                        use_regex=True,
                    )
                else:
                    folder_name = find_folder(
                        base_directory,
                        [group, column[1]] + include_filter,
                        exclude_names=exclude_filter,
                    )
                if folder_name is None:
                    # Skip this data, there is no matching test result
                    continue

                print(folder_name)

                folder_path = os.path.join(base_directory, folder_name)

                # Get all stats
                for stat_name in stat_names:
                    value = extract_stat(folder_path, stat_name[1])
                    file.write(f" {value}")

            file.write("\n")

    print(f"Exported {data_file_name}")

    perf_file_name = filename + ".perf"

    # Try to remove target .perf file if it already exists
    try:
        os.remove(os.path.join(base_directory, perf_file_name))
    except OSError:
        pass

    # Copy the template file to a new file
    shutil.copy(
        os.path.join(
            "configs/integrity_verifier/graphing/gnuplot-templates/",
            perf_template + ".perf",
        ),
        os.path.join(base_directory, perf_file_name),
    )

    with open(os.path.join(base_directory, perf_file_name), "a") as file:
        file.write("\n\n")
        file.write(f'set title "{title}"\n')
        file.write(f'set xlabel "{xlabel}"\n')
        file.write(f'set ylabel "{ylabel}"\n')
        file.write("\n\n")
        file.write(
            f'set output "{os.path.join(base_directory, filename + ".png")}"\n'
        )

        file.write("plot newhistogram '', ")
        file.write(f"'{os.path.join(base_directory, data_file_name)}' using ")
        count = 0
        for i, column in enumerate(columns):
            for j, stat_name in enumerate(stat_names):
                if group_as_xaxis:
                    if count == 0:
                        file.write(
                            f'1:{count + 2} t "{column[0]}, {stat_name[0]}" ls {count + 1}'
                        )
                    else:
                        file.write(
                            f"'' u 1:{count + 2} ti \"{column[0]}, {stat_name[0]}\" ls {count + 1}"
                        )
                else:
                    if count == 0:
                        file.write(
                            f'{count + 2}:xtic(1) t "{column[0]}, {stat_name[0]}" ls {count + 1}'
                        )
                    else:
                        file.write(
                            f"'' u {count + 2} ti \"{column[0]}, {stat_name[0]}\" ls {count + 1}"
                        )
                count += 1

                if j < (len(stat_names) - 1) or i < (len(columns) - 1):
                    file.write(", \\\n")

    print(f"Exported {perf_file_name}")

    # Run gnuplot
    subprocess.run(["gnuplot", os.path.join(base_directory, perf_file_name)])


# Generates .dat files that can be used to graph with gnuplot. (Intended for bar graphs.)
# This is a variation that allows multiple simulations in a grouping of bars. This grabs
# the same one piece (or two pieces) of data from each run.
# The structure is like the following:
# Set       Group     Data    (Secondary Data)
# Set1      Group1    xxx     xxx
# Set1      Group2    xxx     xxx
# Set1      Group3    xxx     xxx
# Set1      Group4    xxx     xxx
# ...
#
#
# Set       Group     Data    (Secondary Data)
# Set2      Group1    xxx     xxx
# ...
#
# Where each group name and set name are keywords in a run.
# When the data is presented in gnuplot, each section/set of data in the .dat file represents one bar in each of the bar clusters.
def data_gen_bars_compare_runs2(
    base_directory,
    filename,  # output filename
    # test,
    groups,  # each collection/cluster of bars
    columns: list[
        tuple[str, str]
    ],  # bars in each cluster. List of tuples: (human readable name, codename used in file names)
    stat_name: tuple[str, str],  # Human readable name, codename used in stats
    secondary_stat: tuple[
        str, str | Callable
    ] = None,  # Human readable name, codename used in stats
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    perf_template: str = "clustered-bars",
    include_filter: list[str] = [],
    exclude_filter: list[str] = [],
    force_remove: bool = False,
):
    data_file_name = filename + ".dat"

    if not force_remove and os.path.isfile(
        os.path.join(base_directory, data_file_name)
    ):
        print(f"{data_file_name} already exists. Skipping.")
        return

    with open(os.path.join(base_directory, data_file_name), "w") as file:
        # Find the test run with the keywords
        folders = [f.name for f in os.scandir(base_directory) if f.is_dir()]

        def find_folder(folders, names, exclude_names: list[str] = []):
            # for folder_name in os.listdir(base_directory):
            for folder_name in folders:
                found = True
                for name in names:
                    if name not in folder_name:
                        # This folder does not have all the keywords
                        found = False
                        break

                for name in exclude_names:
                    if name in folder_name:
                        # This folder contains keywords that are excluded
                        found = False
                        break

                if not found:
                    continue
                # We found a folder with all the keywords to look for
                return folder_name
            return None

        # Each "column"/item/set within each bar cluster
        for i, column in enumerate(columns):
            # Generate first row with column headings.
            file.write(f'Set Group "{stat_name[0]}"')

            # Add secondary stat if applicable.
            if secondary_stat is not None:
                file.write(f' "{secondary_stat[0]}"')

            file.write("\n")

            for group in groups:
                folder_name = find_folder(
                    folders,
                    [group, column[1]] + include_filter,
                    exclude_names=exclude_filter,
                )
                if folder_name is None:
                    # Skip this data, there is no matching test result
                    continue

                file.write(f'"{column[0]}" {group}')

                # print(folder_name)

                folder_path = os.path.join(base_directory, folder_name)

                value = extract_stat(folder_path, stat_name[1])
                if value is None:
                    value = 0.0
                file.write(f" {value}")

                if secondary_stat is not None:
                    if isinstance(secondary_stat[1], str):
                        # Treat this like a single stat.
                        secondary_value = extract_stat(
                            folder_path, secondary_stat[1]
                        )
                        if secondary_value is None:
                            secondary_value = 0.0
                    elif callable(secondary_stat[1]):
                        # Treat this like a custom function.
                        secondary_value = secondary_stat[1](folder_path)
                    file.write(f" {secondary_value}")

                file.write("\n")

            file.write("\n\n")

    print(f"Exported {data_file_name}")

    perf_file_name = filename + ".perf"

    # Try to remove target .perf file if it already exists
    try:
        os.remove(os.path.join(base_directory, perf_file_name))
    except OSError:
        pass

    # Copy the template file to a new file
    shutil.copy(
        os.path.join(
            "configs/integrity_verifier/graphing/gnuplot-templates/",
            perf_template + ".perf",
        ),
        os.path.join(base_directory, perf_file_name),
    )

    with open(os.path.join(base_directory, perf_file_name), "a") as file:
        file.write("\n\n")
        file.write(f'set title "{title}"\n')
        file.write(f'set xlabel "{xlabel}"\n')
        file.write(f'set ylabel "{ylabel}"\n')
        if secondary_stat is not None:
            file.write(f'set cblabel "{secondary_stat[0]}"\n')
            file.write('set palette defined (0 "blue", 1 "red")\n')
            file.write("set cbrange [0:1]\n")
            file.write("set colorbox\n")
        file.write("\n\n")
        file.write(
            f'set output "{os.path.join(base_directory, filename + ".png")}"\n'
        )

        # file.write("plot newhistogram '', ")
        # file.write(f"'{os.path.join(base_directory, data_file_name)}' using ")
        # for i, column in enumerate(columns):
        #     if secondary_stat is None:
        #         if i == 0:
        #             file.write(f"{i + 2}:xtic(1) t \"{column[0]}\" ls {i + 1}")
        #         else:
        #             file.write(f"'' u {i + 2} ti \"{column[0]}\" ls {i + 1}")
        #     else:
        #         # secondary_stat is not None
        #         if i == 0:
        #             file.write(f"($0):{(2*i) + 2}:{(2*i) + 3}:xtic(1) t \"{column[0]}\" ls {i + 1}")
        #         else:
        #             file.write(f"'' u ($0):{(2*i) + 2}:{(2*i) + 3} ti \"{column[0]}\" ls {i + 1}")

        #     if i < (len(columns) - 1):
        #         file.write(", ")

        file.write("plot ")
        for i, column in enumerate(columns):
            if i == 0:
                file.write(
                    f'"{os.path.join(base_directory, data_file_name)}" index {i} using '
                )
                if secondary_stat is not None:
                    file.write("3:4:xtic(2) lc palette z")
                else:
                    file.write("3:xtic(2)")
            else:
                file.write(f"'' index {i} using ")
                if secondary_stat is not None:
                    file.write("3:4 lc palette z")
                else:
                    file.write("3")

            file.write(f" title '{column[0]}'")

            if i < len(columns) - 1:
                file.write(", \\\n")

    print(f"Exported {perf_file_name}")

    # Run gnuplot
    subprocess.run(["gnuplot", os.path.join(base_directory, perf_file_name)])


# Generates data and graphs specifically intended for showing stack distance
# data from WEST-style profiling.
def data_gen_west_points(
    base_directory,
    filename,  # output filename
    test,
    sets: int,  # Number of sets
    distances: int,  # Number of stack distances
    # columns: list[tuple[str, str]], # bars in each cluster. List of tuples: (human readable name, codename used in file names)
    stat_name: tuple[str, str],  # Human readable name, codename used in stats
    # secondary_stat: tuple[str, str] = None, # Human readable name, codename used in stats
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    perf_template: str = "basic",
    include_filter: list[str] = [],
    exclude_filter: list[str] = [],
    force_remove: bool = False,
):
    data_file_name = filename + ".dat"

    if not force_remove and os.path.isfile(
        os.path.join(base_directory, data_file_name)
    ):
        print(f"{data_file_name} already exists. Skipping.")
        return

    with open(os.path.join(base_directory, data_file_name), "w") as file:
        # Find the test run with the keywords
        folders = [f.name for f in os.scandir(base_directory) if f.is_dir()]

        def find_folder(folders, names, exclude_names: list[str] = []):
            for folder_name in folders:
                found = True
                for name in names:
                    if name not in folder_name:
                        # This folder does not have all the keywords
                        found = False
                        break

                for name in exclude_names:
                    if name in folder_name:
                        # This folder contains keywords that are excluded
                        found = False
                        break

                if not found:
                    continue
                # We found a folder with all the keywords to look for
                return folder_name
            return None

        folder_name = find_folder(
            folders, [test] + include_filter, exclude_names=exclude_filter
        )
        folder_path = os.path.join(base_directory, folder_name)
        # print("folder path = " + folder_path)

        # Header row
        # file.write("\"Stack Position\" \"Access Percent\"\n")

        for set in range(sets):
            # Tally up the total sum of accesses.
            access_values = []
            sum = 0.0
            for stack_position in range(distances + 1):
                value = extract_stat(
                    folder_path, stat_name[1] + f"_{set}::{stack_position}"
                )
                if value is None:
                    value = 0.0
                # print(f"{stat_name[1]}_{set}::{stack_position} = {value}")
                access_values.append(value)
                sum += value
                assert access_values[stack_position] == value

            # if sum == 0:
            #     print(f"{stat_name[1]}_{set}::{stack_position}")

            # Write the proportion of each stack position.
            for stack_position in range(distances + 1):
                file.write(
                    f"{stack_position} {access_values[stack_position] / sum}\n"
                )

    print(f"Exported {data_file_name}")

    perf_file_name = filename + ".perf"

    # Try to remove target .perf file if it already exists
    try:
        os.remove(os.path.join(base_directory, perf_file_name))
    except OSError:
        pass

    # Copy the template file to a new file
    shutil.copy(
        os.path.join(
            "configs/integrity_verifier/graphing/gnuplot-templates/",
            perf_template + ".perf",
        ),
        os.path.join(base_directory, perf_file_name),
    )

    with open(os.path.join(base_directory, perf_file_name), "a") as file:
        file.write("\n\n")
        file.write(f'set title "{title}"\n')
        file.write(f'set xlabel "{xlabel}"\n')
        file.write(f'set ylabel "{ylabel}"\n')
        file.write(f"set xrange [-1:{distances+1}]\n")
        file.write("\n\n")
        file.write(
            f'set output "{os.path.join(base_directory, filename + ".png")}"\n'
        )

        file.write(
            f'plot "{os.path.join(base_directory, data_file_name)}" notitle\n'
        )

    print(f"Exported {perf_file_name}")

    # Run gnuplot
    subprocess.run(["gnuplot", os.path.join(base_directory, perf_file_name)])


# Take a set of simulations and have one point in a plot per simulation.
# Per simulation, one stat represents the X coordinate, and another stat represents the
# Y coordinate.
def data_gen_coordinates(
    base_directory,
    filename,  # output filename
    tests,  # The names of simulations to use
    x_stat: str,  # Codename used in stats
    y_stat: str,  # Codename used in stats
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    perf_template: str = "basic",
    include_filter: list[str] = [],
    exclude_filter: list[str] = [],
    use_regex: bool = False,
    force_remove: bool = False,
):
    data_file_name = filename + ".dat"

    if not force_remove and os.path.isfile(
        os.path.join(base_directory, data_file_name)
    ):
        print(f"{data_file_name} already exists. Skipping.")
        return

    with open(os.path.join(base_directory, data_file_name), "w") as file:
        # No headings.
        # # Generate first row with column headings.
        # if secondary_stat is None:
        #     # Use standard column headings.
        #     file.write(f"Group {' '.join(['"' + column[0] + '"' for column in columns])}\n")
        # else:
        #     # Alternate headings to add the secondary stat.
        #     file.write(f"Group {' '.join(['"' + column[0] + '" "' + column[0] + ' - ' + secondary_stat[0] + '"' for column in columns])}\n")

        # Each row (simulation run)
        for test in tests:
            # Find the test run with the keywords
            def find_folder(
                base_directory,
                names,
                exclude_names: list[str] = [],
                regex="",
                use_regex: bool = False,
            ):
                for folder_name in os.listdir(base_directory):
                    found = True

                    # This folder does not match the regex
                    if use_regex and not re.search(regex, folder_name):
                        found = False

                    for name in names:
                        if name not in folder_name:
                            # This folder does not have all the keywords
                            found = False
                            break

                    for name in exclude_names:
                        if name in folder_name:
                            # This folder contains keywords that are excluded
                            found = False
                            break

                    if not found:
                        continue
                    # We found a folder with all the keywords to look for
                    return folder_name
                return None

            # file.write(f"{test}")

            # Each column
            if use_regex:
                folder_name = find_folder(
                    base_directory,
                    include_filter,
                    exclude_names=exclude_filter,
                    regex=test,
                    use_regex=True,
                )
            else:
                folder_name = find_folder(
                    base_directory,
                    [test] + include_filter,
                    exclude_names=exclude_filter,
                )
            if folder_name is None:
                # Skip this data, there is no matching test result
                continue

            print(folder_name)

            folder_path = os.path.join(base_directory, folder_name)

            x_value = extract_stat(folder_path, x_stat)
            file.write(f"{x_value}")

            y_value = extract_stat(folder_path, y_stat)
            file.write(f" {y_value}")

            file.write("\n")

    print(f"Exported {data_file_name}")

    perf_file_name = filename + ".perf"

    # Try to remove target .perf file if it already exists
    try:
        os.remove(os.path.join(base_directory, perf_file_name))
    except OSError:
        pass

    # Copy the template file to a new file
    shutil.copy(
        os.path.join(
            "configs/integrity_verifier/graphing/gnuplot-templates/",
            perf_template + ".perf",
        ),
        os.path.join(base_directory, perf_file_name),
    )

    with open(os.path.join(base_directory, perf_file_name), "a") as file:
        file.write("\n\n")
        file.write(f'set title "{title}"\n')
        file.write(f'set xlabel "{xlabel}"\n')
        file.write(f'set ylabel "{ylabel}"\n')
        file.write("\n\n")
        file.write(
            f'set output "{os.path.join(base_directory, filename + ".png")}"\n'
        )

        file.write(
            f'plot "{os.path.join(base_directory, data_file_name)}" notitle\n'
        )

    print(f"Exported {perf_file_name}")

    # Run gnuplot
    subprocess.run(["gnuplot", os.path.join(base_directory, perf_file_name)])


# Take a set of simulations and have one point in a plot per simulation.
# Per simulation, one stat represents the Y coordinate. Simple scatter plot.
def data_gen_simple(
    base_directory,
    filename,  # output filename
    tests,  # The names of simulations to use
    stat: str,  # Codename used in stats
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    perf_template: str = "basic",
    include_filter: list[str] = [],
    exclude_filter: list[str] = [],
    use_regex: bool = False,
    force_remove: bool = False,
):
    data_file_name = filename + ".dat"

    if not force_remove and os.path.isfile(
        os.path.join(base_directory, data_file_name)
    ):
        print(f"{data_file_name} already exists. Skipping.")
        return

    with open(os.path.join(base_directory, data_file_name), "w") as file:
        # No headings.
        # # Generate first row with column headings.
        # if secondary_stat is None:
        #     # Use standard column headings.
        #     file.write(f"Group {' '.join(['"' + column[0] + '"' for column in columns])}\n")
        # else:
        #     # Alternate headings to add the secondary stat.
        #     file.write(f"Group {' '.join(['"' + column[0] + '" "' + column[0] + ' - ' + secondary_stat[0] + '"' for column in columns])}\n")

        # Each row (simulation run)
        for test in tests:
            # Find the test run with the keywords
            def find_folder(
                base_directory,
                names,
                exclude_names: list[str] = [],
                regex="",
                use_regex: bool = False,
            ):
                for folder_name in os.listdir(base_directory):
                    found = True

                    # This folder does not match the regex
                    if use_regex and not re.search(regex, folder_name):
                        found = False

                    for name in names:
                        if name not in folder_name:
                            # This folder does not have all the keywords
                            found = False
                            break

                    for name in exclude_names:
                        if name in folder_name:
                            # This folder contains keywords that are excluded
                            found = False
                            break

                    if not found:
                        continue
                    # We found a folder with all the keywords to look for
                    return folder_name
                return None

            # file.write(f"{test}")

            # Each column
            if use_regex:
                folder_name = find_folder(
                    base_directory,
                    include_filter,
                    exclude_names=exclude_filter,
                    regex=test,
                    use_regex=True,
                )
            else:
                folder_name = find_folder(
                    base_directory,
                    [test] + include_filter,
                    exclude_names=exclude_filter,
                )
            if folder_name is None:
                # Skip this data, there is no matching test result
                continue

            print(folder_name)

            folder_path = os.path.join(base_directory, folder_name)

            value = extract_stat(folder_path, stat)
            file.write(f"{value}")

            file.write("\n")

    print(f"Exported {data_file_name}")

    perf_file_name = filename + ".perf"

    # Try to remove target .perf file if it already exists
    try:
        os.remove(os.path.join(base_directory, perf_file_name))
    except OSError:
        pass

    # Copy the template file to a new file
    shutil.copy(
        os.path.join(
            "configs/integrity_verifier/graphing/gnuplot-templates/",
            perf_template + ".perf",
        ),
        os.path.join(base_directory, perf_file_name),
    )

    with open(os.path.join(base_directory, perf_file_name), "a") as file:
        file.write("\n\n")
        file.write(f'set title "{title}"\n')
        file.write(f'set xlabel "{xlabel}"\n')
        file.write(f'set ylabel "{ylabel}"\n')
        file.write("\n\n")
        file.write(
            f'set output "{os.path.join(base_directory, filename + ".png")}"\n'
        )

        file.write(
            f'plot "{os.path.join(base_directory, data_file_name)}" notitle\n'
        )

    print(f"Exported {perf_file_name}")

    # Run gnuplot
    subprocess.run(["gnuplot", os.path.join(base_directory, perf_file_name)])


def add_arguments(parser):
    parser.add_argument(
        "--base-dir",
        type=str,
        required=True,
        help="Directory with all gem5 runs.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        required=False,
        help="Replace files if they already exist.",
    )

    return parser


def main(base_directory):
    everything = os.listdir(base_directory)

    data_gen_bars_compare_runs(
        base_directory,
        filename="cxl-read-bandwidth",
        # test="",
        groups=[
            "parsec-" + benchmark + "-simsmall"
            for benchmark in parsec_benchmarks
            if benchmark not in ["facesim", "x264"]
        ]
        + ["micro-shortwiderandom", "micro-skippass"],
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
            "CXL Read Bandwidth",
            "board.cxl_comm_monitor.averageReadBandwidth",
        ),
        # secondary_stat=(
        #     "LLC miss rate",
        #     "board.cache_hierarchy.l2cache.demandMissRate::total",
        # ),
        # secondary_stat=(
        #     "Metadata Cache Miss Rate",
        #     "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRate",
        # ),
        title="CXL Read Bandwidth",
        xlabel="Benchmark",
        ylabel="Read Bandwidth (B)",
        # include_filter=["app"],
        exclude_filter=["PageSwapYes"],
    )

    # Time to simulate
    data_gen_bars(
        base_directory,
        filename="simtime",
        test="",
        # configurations=["parsec-" + benchmark + "-simsmall" for benchmark in parsec_benchmarks if benchmark not in ["facesim", "x264"]] + ["micro-shortwiderandom", "micro-skippass"],
        configurations=[
            "parsec-" + benchmark + "-simsmall"
            for benchmark in parsec_benchmarks
        ]
        + ["micro-shortwiderandom", "micro-skippass"],
        # configurations=everything,
        stat_names=[
            (
                "Wall Clock Time",
                "hostSeconds",
            ),
        ],
        title="Wall Clock Time for Simulation",
        xlabel="Benchmark",
        ylabel="Time",
        include_filter=["app-dram"],
        exclude_filter=["integrity"],
    )

    data_gen_bars_compare_runs(
        base_directory,
        filename="simtime-all",
        # test="",
        groups=[
            "parsec-" + benchmark + "-simsmall"
            for benchmark in parsec_benchmarks
            if benchmark not in ["facesim", "x264"]
        ]
        + ["micro-shortwiderandom", "micro-skippass"],
        # groups=["parsec-" + benchmark + "-simsmall" for benchmark in parsec_benchmarks] + ["micro-shortwiderandom", "micro-skippass"],
        columns=[
            (
                "DRAM Only (No integrity)",
                "app-dram-only",
            ),
            (
                "CXL only (No integrity)",
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
            "Wall Clock Time",
            "hostSeconds",
        ),
        title="Wall Clock Time for Simulation",
        xlabel="Benchmark",
        ylabel="Time",
        # include_filter=["app"],
        exclude_filter=["PageSwapYes"],
    )

    data_gen_bars_compare_runs(
        base_directory,
        filename="runtime-all",
        # test="",
        groups=[
            "parsec-" + benchmark + "-simsmall"
            for benchmark in parsec_benchmarks
            if benchmark not in ["facesim", "x264"]
        ]
        + ["micro-shortwiderandom", "micro-skippass"],
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
            "runtime",
            "simSeconds",
        ),
        title="Execution time",
        xlabel="Benchmark",
        ylabel="Time",
        # include_filter=["app"],
        exclude_filter=["PageSwapYes"],
    )

    data_gen_bars_compare_runs(
        base_directory,
        filename="llc-latency-all",
        # test="",
        groups=[
            "parsec-" + benchmark + "-simsmall"
            for benchmark in parsec_benchmarks
            if benchmark not in ["facesim", "x264"]
        ]
        + ["micro-shortwiderandom", "micro-skippass"],
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
            "LLC Miss Latency",
            "board.cache_hierarchy.l2cache.demandAvgMissLatency::total",
        ),
        # secondary_stat=(
        #     "LLC miss rate",
        #     "board.cache_hierarchy.l2cache.demandMissRate::total",
        # ),
        # secondary_stat=(
        #     "Metadata Cache Miss Rate",
        #     "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRate",
        # ),
        title="LLC Miss Latency",
        xlabel="Benchmark",
        ylabel="Latency (ps)",
        # include_filter=["app"],
        exclude_filter=["PageSwapYes"],
    )

    data_gen_bars_compare_runs2(
        base_directory,
        filename="llc-latency-all2",
        # test="",
        groups=[
            "parsec-" + benchmark + "-simsmall"
            for benchmark in parsec_benchmarks
            if benchmark not in ["facesim", "x264"]
        ]
        + ["micro-shortwiderandom", "micro-skippass"],
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
            "LLC Miss Latency",
            "board.cache_hierarchy.l2cache.demandAvgMissLatency::total",
        ),
        # secondary_stat=(
        #     "LLC miss rate",
        #     "board.cache_hierarchy.l2cache.demandMissRate::total",
        # ),
        secondary_stat=(
            "Metadata Cache Miss Rate",
            "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRate",
        ),
        title="LLC Miss Latency",
        xlabel="Benchmark",
        ylabel="Latency (ps)",
        # include_filter=["app"],
        exclude_filter=["PageSwapYes"],
    )

    graphs = [
        {
            "filename": "verifier-latency",
            "stat": "board.cache_hierarchy.verifier.integrity_verifier.avgDataReqLatency",
            "title": "Average Data Request Latency (From Verifier)",
            "ylabel": "Latency (ps)",
        },
        {
            "filename": "metadata-miss-rate",
            "stat": "board.cache_hierarchy.verifier.integrity_verifier.metadataCacheMissRate",
            "title": "Metadata Cache Miss Rate",
            "ylabel": "Rate",
        },
        {
            "filename": "llc-miss-rate",
            "stat": "board.cache_hierarchy.l2cache.demandMissRate::total",
            "title": "LLC Miss Rate",
            "ylabel": "Rate",
        },
    ]
    for item in graphs:
        data_gen_bars_compare_runs(
            base_directory,
            filename=f"{item['filename']}-all",
            # test="",
            groups=[
                "parsec-" + benchmark + "-simsmall"
                for benchmark in parsec_benchmarks
                if benchmark not in ["facesim", "x264"]
            ]
            + ["micro-shortwiderandom", "micro-skippass"],
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
                item["title"],
                item["stat"],
            ),
            title=item["title"],
            xlabel="Benchmark",
            ylabel=item["ylabel"],
            # include_filter=["app"],
            exclude_filter=["PageSwapYes"],
        )

    # # Comparing time to simulate and simulated time
    # data_gen_bars(
    #     base_directory,
    #     filename="guesttime",
    #     test="",
    #     configurations=["parsec-" + benchmark + "-simsmall" for benchmark in parsec_benchmarks],
    #     # configurations=[
    #     #     "parsec-blackscholes-simsmall",
    #     #     "parsec-bodytrack-simsmall",
    #     #     "parsec-canneal-simsmall",
    #     #     "parsec-dedup-simsmall",
    #     #     "parsec-facesim-simsmall",
    #     #     "parsec-ferret-simsmall",
    #     #     "parsec-fluidanimate-simsmall",
    #     #     "parsec-freqmine-simsmall",
    #     #     "parsec-raytrace-simsmall",
    #     #     "parsec-streamcluster-simsmall",
    #     #     "parsec-swaptions-simsmall",
    #     #     "parsec-vips-simsmall",
    #     #     "parsec-x264-simsmall",
    #     # ],
    #     stat_names=[
    #         (
    #             "guesttime",
    #             "simSeconds",
    #         ),
    #         (
    #             "simtime",
    #             "hostSeconds",
    #         ),
    #     ],
    #     title="",
    #     xlabel="",
    #     ylabel="",
    # )

    # Stacked graphs that show proportion of requests handled,
    # either with or without page swapping
    data_gen_stacked(
        base_directory,
        filename=f"skippass-reqHandled",
        test="skippass",
        groups=[
            "PageSwapNo_CxlLat35ns",
            # 'PageSwapNo_CxlLat70ns',
            "PageSwapYes_CxlLat35ns",
            # 'PageSwapYes_CxlLat70ns',
        ],
        configurations=[
            "app-dram-integrity-dram",
            "app-dram-integrity-cxl",
            "app-cxl-integrity-dram",
            "app-cxl-integrity-cxl",
        ],
        stacked_names=[
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
        title="Number of requests processed below LLC",
        xlabel="Configuration",
        ylabel="Number of Requests (Count)",
    )

    # Latency time with or without page swapping
    data_gen_stacked(
        base_directory,
        filename=f"skippass-latency",
        test="skippass",
        groups=[
            "PageSwapNo_CxlLat35ns",
            # 'PageSwapNo_CxlLat70ns',
            "PageSwapYes_CxlLat35ns",
            # 'PageSwapYes_CxlLat70ns',
        ],
        configurations=[
            "app-dram-integrity-dram",
            "app-dram-integrity-cxl",
            "app-cxl-integrity-dram",
            "app-cxl-integrity-cxl",
        ],
        stacked_names=[
            (
                "fromLLC",
                "board.cache_hierarchy.l2cache.overallAvgMissLatency::total",
            ),
            (
                "fromVerifier",
                "board.cache_hierarchy.verifier.integrity_verifier.avgReqLatency",
            ),
            (
                "fromPageSwapper",
                "board.cache_hierarchy.page_swapper.page_swapper.avgReqLatency",
            ),
        ],
        title="LLC Cache Miss Latency",
        xlabel="Configuration",
        ylabel="Latency (ps)",
    )

    # test = "shortwiderandom"
    # filename = f"{test}-reqHandled.perf"
    # data_gen_stackedbars(
    #     base_directory,
    #     filename,
    #     test=test,
    #     groups=groups,
    #     configurations=configurations,
    #     stacked_names=stacked_names,
    #     title="Number of requests processed below LLC",
    #     xlabel="Configuration",
    #     ylabel="Number of Requests (Count)",
    # )
    # print(f"Exported {filename}")

    # test = "skippass"
    # stacked_names = [
    #     (
    #         "fromLLC",
    #         "board.cache_hierarchy.l2cache.overallAvgMissLatency::total",
    #     ),
    #     (
    #         "fromVerifier",
    #         "board.cache_hierarchy.verifier.integrity_verifier.avgReqLatency",
    #     ),
    #     (
    #         "fromPageSwapper",
    #         "board.cache_hierarchy.page_swapper.page_swapper.avgReqLatency",
    #     ),
    # ]

    # filename = f"{test}-latency.perf"
    # data_gen_stackedbars(
    #     base_directory,
    #     filename,
    #     test=test,
    #     groups=groups,
    #     configurations=configurations,
    #     stacked_names=stacked_names,
    #     title="LLC Cache miss latency",
    #     xlabel="Configuration",
    #     ylabel="Latency (ps)",
    # )
    # print(f"Exported {filename}")

    # test = "shortwiderandom"
    # filename = f"{test}-latency.perf"
    # data_gen_stackedbars(
    #     base_directory,
    #     filename,
    #     test=test,
    #     groups=groups,
    #     configurations=configurations,
    #     stacked_names=stacked_names,
    #     title="LLC Cache miss latency",
    #     xlabel="Configuration",
    #     ylabel="Latency (ps)",
    # )
    # print(f"Exported {filename}")

    return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export many gem5 runs into data files for gnuplot."
    )
    add_arguments(parser)
    args = parser.parse_args()

    if args.force:
        force_remove = True

    # base_directory = (
    #     "./output/testsuite7"  # Change this to your base directory
    # )
    base_directory = args.base_dir
    main(base_directory)
