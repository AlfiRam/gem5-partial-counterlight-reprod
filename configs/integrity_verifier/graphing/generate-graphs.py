#!/usr/bin/env python3

import os

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


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
    return stat_val


def group_from_folder_name(folder_name, grouping_indexes):
    """Extract the grouping parameter from the folder name."""
    parts = folder_name.split("_")
    selected_parts = []
    for i, part in enumerate(parts):
        if i in grouping_indexes:
            selected_parts.append(part)

    return "_".join(selected_parts)
    # Example: return the second and third parts as a group
    # return '_'.join(parts[1:2])
    # Adjust indices based on grouping needs
    # return parts[index]


def generate_data_structure(
    base_directory,
    internal_stat_name,
    data_stat_name,
    include_test_name: bool,
    grouping_indexes,
):
    data = []

    # Iterate through each folder in the base directory
    for folder_name in os.listdir(base_directory):
        # Ignore some runs
        if "TimingTree_PartitionedMetadataCache" in folder_name:
            continue
        elif "TimingBmt_MetadataCache" in folder_name:
            continue
        if not (
            "TimingBmt" in folder_name
            and "PartitionedMetadataCache" in folder_name
        ):
            continue

        original_folder_name = folder_name

        folder_path = os.path.join(base_directory, folder_name)
        if os.path.isdir(folder_path):
            stat_value = extract_stat(folder_path, internal_stat_name)

            if stat_value is not None:
                group = group_from_folder_name(folder_name, grouping_indexes)
                if "integrity" not in folder_name:
                    folder_name += "_NoTree_NoMetadataCache"

                # Remove the group part from FullFolderName
                # Adjust indices based on grouping needs, exclude group parts
                remaining_parts = []
                for i, part in enumerate(folder_name.split("_")):
                    if (i == 0 and include_test_name) or (
                        i != 0 and i not in grouping_indexes
                    ):
                        remaining_parts.append(part)

                # if include_test_name:
                #     remaining_parts = [folder_name.split('_')[0]] + folder_name.split('_')[2:]
                # else:
                #     remaining_parts = folder_name.split('_')[2:]
                # Version of the folder name that takes out the group name
                grouped_folder_name = "_____".join(remaining_parts)

                test_name = folder_name.split("_")[0]

                data.append(
                    {
                        "Group": group,
                        "GroupedFolderName": grouped_folder_name,
                        data_stat_name: stat_value,
                        "TestName": test_name,
                        "OriginalFolderName": original_folder_name,
                    }
                )

    return data


def generate_plot(
    base_directory,
    internal_stat_name,
    data_stat_name,
    title,
    xlabel,
    ylabel,
    grouping_indexes,
    split_by_test: bool = True,
    normalize: bool = False,
    normalization_test: str = "",
):
    data = generate_data_structure(
        base_directory,
        internal_stat_name,
        data_stat_name,
        include_test_name=not split_by_test,
        grouping_indexes=grouping_indexes,
    )

    # Create a DataFrame from the collected data
    df = pd.DataFrame(data)

    # Calculate normalization data
    # Sort the DataFrame by Group and FullFolderName
    df.sort_values(by=["TestName", "Group", "GroupedFolderName"], inplace=True)

    if normalize:
        ylabel += " (Normalized)"

    if split_by_test:
        unique_tests = df["TestName"].unique()

        # Create separate plots for each group
        original_data_stat_name = data_stat_name
        for test in unique_tests:
            if normalize:
                selected_entry = df[
                    df["OriginalFolderName"].str.contains(normalization_test)
                    & df["TestName"].str.contains(test)
                ].iloc[0]
                normalization_value = selected_entry[original_data_stat_name]
                df[f"{original_data_stat_name}_Normalized"] = (
                    df[original_data_stat_name] / normalization_value
                )
                data_stat_name = f"{original_data_stat_name}_Normalized"
            test_data = df[df["TestName"] == test]

            export_plot(
                test_data,
                data_stat_name,
                title + " - " + test,
                xlabel,
                ylabel,
                f"{data_stat_name}_plot_{test}.svg",
                dotted_line_value=1 if normalize else None,
            )

    else:
        if normalize:
            selected_entry = df[
                df["OriginalFolderName"].str.contains(normalization_test)
            ].iloc[0]
            normalization_value = selected_entry[data_stat_name]
            df[f"{data_stat_name}_Normalized"] = (
                df[data_stat_name] / normalization_value
            )
            ylabel += " (Normalized)"
        export_plot(
            df,
            data_stat_name,
            title,
            xlabel,
            ylabel,
            f"{data_stat_name}_plot.svg",
            dotted_line_value=1 if normalize else None,
        )


def export_plot(
    df,
    data_stat_name,
    title,
    xlabel,
    ylabel,
    output_file,
    dotted_line_value: int = None,
):
    max_label_length = df["GroupedFolderName"].str.len().max()
    fig_width = 12
    height_factor = 0.115
    fig_height = max_label_length * height_factor

    # Plotting
    plt.figure(figsize=(fig_width, fig_height))
    bp = sns.barplot(
        x="GroupedFolderName",
        y=data_stat_name,
        hue="Group",
        data=df,
        errorbar=None,
        zorder=3,
    )
    plt.grid(color="grey", linestyle="-", linewidth=0.5, alpha=0.6, zorder=0)
    plt.xticks(
        rotation=45, ha="right"
    )  # Rotate x labels for better readability
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    sns.move_legend(bp, "upper left", bbox_to_anchor=(1, 1))

    if dotted_line_value:
        plt.axhline(
            y=dotted_line_value,
            color="red",
            linestyle="--",
            label="Dotted Line at 0.5",
            zorder=4,
        )

    plt.tight_layout()

    # Save the plot as an SVG file
    output_file = os.path.join(base_directory, output_file)
    plt.savefig(output_file, format="svg")
    plt.close()  # Close the plot to free up memory

    print(f"Plot saved as {output_file}")


def main(base_directory):
    generate_plot(
        base_directory=base_directory,
        internal_stat_name="simSeconds",
        data_stat_name="SimSeconds",
        title="Execution Time",
        xlabel="Tree Configuration",
        ylabel="Execution Time (s)",
        grouping_indexes=[1],
        split_by_test=True,
    )

    generate_plot(
        base_directory=base_directory,
        internal_stat_name="simSeconds",
        data_stat_name="SimSeconds",
        title="Execution Time",
        xlabel="Tree Configuration",
        ylabel="Execution Time (s)",
        grouping_indexes=[1],
        split_by_test=True,
        normalize=True,
        normalization_test="app-dram-integrity-dram_TimingBmt_PartitionedMetadataCache_PageSwapNo",
    )

    generate_plot(
        base_directory=base_directory,
        internal_stat_name="board.cache_hierarchy.verifier.integrity_verifier.avgDataReqLatency",
        data_stat_name="DataReqLatency",
        title="Average Data Request Latency",
        xlabel="Tree Configuration",
        ylabel="Latency (ps)",
        grouping_indexes=[1],
        split_by_test=True,
    )

    generate_plot(
        base_directory=base_directory,
        internal_stat_name="board.cache_hierarchy.l2cache.demandAvgMissLatency::total",
        data_stat_name="L2Latency",
        title="LLC Average Miss Latency",
        xlabel="Tree Configuration",
        ylabel="Average Miss Latency (ps)",
        grouping_indexes=[1],
        split_by_test=True,
    )

    generate_plot(
        base_directory=base_directory,
        internal_stat_name="board.cache_hierarchy.verifier.integrity_verifier.reqHandledDramOs",
        data_stat_name="DramOsReqs",
        title="Number of (Non-Integrity) Requests For DRAM",
        xlabel="Tree Configuration",
        ylabel="Requests (Count)",
        grouping_indexes=[1],
        split_by_test=True,
    )

    generate_plot(
        base_directory=base_directory,
        internal_stat_name="board.cache_hierarchy.verifier.integrity_verifier.metadataCacheHitRate",
        data_stat_name="MetadataCacheHitRate",
        title="Metadata Cache Hit Rate",
        xlabel="Tree Configuration",
        ylabel="Rate",
        grouping_indexes=[1],
        split_by_test=True,
    )

    generate_plot(
        base_directory=base_directory,
        internal_stat_name="board.cache_hierarchy.l2cache.demandMissRate::total",
        data_stat_name="L2MissRate",
        title="LLC Miss Rate",
        xlabel="Tree Configuration",
        ylabel="Rate",
        grouping_indexes=[1],
        split_by_test=True,
    )


if __name__ == "__main__":
    base_directory = (
        "./output/testsuite7"  # Change this to your base directory
    )
    main(base_directory)
