#!/usr/bin/env python3


import argparse
import os
import queue
import re
import signal
import subprocess
import threading
import time

processes = []

total_runs = 0
error_runs = []


def add_arguments(parser):
    parser.add_argument(
        "--gem5",
        type=str,
        required=True,
        choices=[
            "opt",
            "debug",
        ],
    )

    parser.add_argument(
        "--test-group",
        type=str,
        required=True,
        help="Group to place all tests into.",
    )

    parser.add_argument(
        "--benchmark",
        type=str,
        required=True,
        nargs="+",
        # choices=[
        #     "demo-demo",
        #     "micro-shortwidepass",
        #     "micro-shortwidepass2",
        #     "micro-widepass",
        #     "micro-widepass2",
        #     "micro-widerandom",
        #     "parsec-blackscholes",
        # ]
    )

    parser.add_argument(
        "--configuration",
        type=str,
        required=True,
        nargs="+",
        choices=[
            "app-dram-integrity-dram",
            "app-dram-integrity-cxl",
            "app-cxl-integrity-dram",
            "app-cxl-integrity-cxl",
            "app-dram",
            "app-cxl",
        ],
    )

    parser.add_argument(
        "--cxl-latency",
        type=str,
        required=False,
        nargs="+",
    )

    parser.add_argument(
        "--tree-type",
        type=str,
        required=True,
        nargs="+",
        choices=[
            "TimingTree",
            "TimingBmt",
            "None",
        ],
    )

    parser.add_argument(
        "--cache-type",
        type=str,
        required=True,
        nargs="+",
        choices=[
            "MetadataCache",
            "PartitionedMetadataCache",
        ],
    )

    parser.add_argument(
        "--page-swap",
        type=str,
        required=False,
        default="No",
        nargs="+",
        choices=[
            "Yes",
            "No",
        ],
    )

    parser.add_argument(
        "--debug-flags",
        type=str,
        required=False,
        help="Same as --debug-flags parameter used in gem5. Write flags in comma-separated list.",
    )

    return parser


# Parse configuration details and create a gem5 command to run.
def compile_command(
    args,
    benchmark: str,
    configuration: str,
    tree_type: str = None,
    metadata_cache_type: str = None,
    page_swap: str = None,
    cxl_latency: str = None,
):
    match args.gem5:
        case "opt":
            gem5_binary = "./build/X86/gem5.opt"
        case "debug":
            gem5_binary = "./build/X86/gem5.debug"
        case _:
            print(f"Unknown gem5 type '{args.gem5}'")
            exit(1)

    gem5_params = "--listener-mode=on"
    if args.debug_flags:
        gem5_params += " --debug-flags=" + args.debug_flags

    # if args.redirect_stdout:
    #     gem5_params += " --redirect-stdout --stdout-file stdout.txt --redirect-stderr --stderr-file stderr.txt"

    home = os.environ.get("HOME")
    custom_img_path = f"{home}/Documents/gem5-resources/src/custom-imgs"
    if "demo-" in benchmark:
        # Demo benchmark.
        config_file = "configs/integrity_verifier/basic-demo.py"
    elif "micro-" in benchmark:
        # This must be a microbenchmark.
        config_file = (
            "configs/integrity_verifier/x86-microbenchmarks-ubuntu-22.py"
        )
        resource_build_path = f"{custom_img_path}/build-microbenchmarks-22-04"
        kernel_path = f"{resource_build_path}/vmlinux-x86-ubuntu"
        img_path = f"{resource_build_path}/microbenchmarks-22-04"
    elif "parsec-" in benchmark:
        # This must be a PARSEC benchmark.
        config_file = "configs/integrity_verifier/x86-parsec-ubuntu-22.py"
        resource_build_path = f"{custom_img_path}/build-parsec-22-04"
        kernel_path = f"{resource_build_path}/vmlinux-x86-ubuntu"
        img_path = f"{resource_build_path}/parsec-22-04"
    else:
        print(f"Unknown benchmark prefix in '{benchmark}'.")
        exit(1)

    match benchmark:
        case "demo-demo":
            benchmark_params = ""

        case "micro-shortwidepass":
            benchmark_name = "widepass"
            benchmark_params = f"--benchmark {benchmark_name} --page-size=4096 --page-count=10 --passes=30 --kernel-path {kernel_path} --img-path {img_path}"
        case "micro-shortwidepass2":
            benchmark_name = "widepass"
            benchmark_params = f"--benchmark {benchmark_name} --page-size=4096 --page-count=10 --passes=500 --kernel-path {kernel_path} --img-path {img_path}"
        case "micro-skippass":
            benchmark_name = "skippass"
            benchmark_params = f"--benchmark {benchmark_name} --page-size=4096 --page-count=5000 --passes=20 --kernel-path {kernel_path} --img-path {img_path}"
        case "micro-widepass":
            benchmark_name = "widepass"
            benchmark_params = f"--benchmark {benchmark_name} --page-size=4096 --page-count=3000 --passes=2 --kernel-path {kernel_path} --img-path {img_path}"
        case "micro-widepass2":
            benchmark_name = "widepass"
            benchmark_params = f"--benchmark {benchmark_name} --page-size=4096 --page-count=3000 --passes=5 --kernel-path {kernel_path} --img-path {img_path}"
        case "micro-widepass3":
            benchmark_name = "widepass"
            benchmark_params = f"--benchmark {benchmark_name} --page-size=4096 --page-count=5000 --passes=20 --kernel-path {kernel_path} --img-path {img_path}"
        case "micro-widerandom":
            benchmark_name = "widerandom"
            benchmark_params = f"--benchmark {benchmark_name} --page-size=4096 --page-count=3000 --passes=200000 --kernel-path {kernel_path} --img-path {img_path}"
        case "micro-shortwiderandom":
            benchmark_name = "widerandom"
            benchmark_params = f"--benchmark {benchmark_name} --page-size=4096 --page-count=4000 --passes=50000 --kernel-path {kernel_path} --img-path {img_path}"

        # PARSEC
        # Full list: parsec-blackscholes parsec-bodytrack parsec-canneal parsec-dedup parsec-facesim parsec-ferret parsec-fluidanimate parsec-freqmine parsec-raytrace parsec-streamcluster parsec-swaptions parsec-vips parsec-x264
        case "parsec-blackscholes":
            benchmark_name = "blackscholes"
            size = "simmedium"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"
        case "parsec-blackscholes-large":
            benchmark_name = "blackscholes"
            size = "simlarge"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"
        case "parsec-bodytrack":
            benchmark_name = "bodytrack"
            size = "simmedium"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"
        case "parsec-canneal":
            benchmark_name = "canneal"
            size = "simmedium"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"
        case "parsec-dedup":
            benchmark_name = "dedup"
            size = "simmedium"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"
        case "parsec-facesim":
            benchmark_name = "facesim"
            size = "simmedium"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"
        case "parsec-ferret":
            benchmark_name = "ferret"
            size = "simmedium"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"
        case "parsec-fluidanimate":
            benchmark_name = "fluidanimate"
            size = "simmedium"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"
        case "parsec-freqmine":
            benchmark_name = "freqmine"
            size = "simmedium"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"
        case "parsec-raytrace":
            benchmark_name = "raytrace"
            size = "simmedium"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"
        case "parsec-streamcluster":
            benchmark_name = "streamcluster"
            size = "simmedium"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"
        case "parsec-swaptions":
            benchmark_name = "swaptions"
            size = "simmedium"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"
        case "parsec-vips":
            benchmark_name = "vips"
            size = "simmedium"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"
        case "parsec-x264":
            benchmark_name = "x264"
            size = "simmedium"
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"

        case _:
            print(f"Unknown benchmark '{benchmark}'")
            exit(1)

    common_config_params = ""
    match configuration:
        case "app-dram-integrity-dram":
            # configuration_params="--use-integrity-verifier --dram-size=3GiB --cxl-size=0 --integrity-allocation-mode=DramOnly"
            configuration_params = "--use-integrity-verifier --dram-size=3GiB --integrity-allocation-mode=DramOnly"
        case "app-dram-integrity-cxl":
            # configuration_params="--use-integrity-verifier --enable-cxl --dram-size=3GiB --cxl-size=2GiB --integrity-allocation-mode=CxlOnly --no-cxl-for-apps"
            # configuration_params="--use-integrity-verifier --dram-size=3GiB --cxl-mode=PCIe --cxl-size=2GiB --integrity-allocation-mode=CxlOnly --no-apps-on-secondary-memory"
            configuration_params = "--use-integrity-verifier --dram-size=3GiB --cxl-mode=DRAM --cxl-size=2GiB --integrity-allocation-mode=CxlOnly --no-apps-on-secondary-memory"
        case "app-cxl-integrity-dram":
            # configuration_params="--use-integrity-verifier --enable-cxl --dram-size=3GiB --dram-os-size=256MiB --cxl-size=2GiB --integrity-allocation-mode=DramOnly"
            # configuration_params="--use-integrity-verifier --dram-size=3GiB --dram-os-size=256MiB --cxl-mode=PCIe --cxl-size=2GiB --integrity-allocation-mode=DramOnly"
            configuration_params = "--use-integrity-verifier --dram-size=3GiB --dram-os-size=256MiB --cxl-mode=DRAM --cxl-size=2GiB --integrity-allocation-mode=DramOnly"
        case "app-cxl-integrity-cxl":
            # configuration_params="--use-integrity-verifier --enable-cxl --dram-size=256MiB --dram-os-size=256MiB --little-dram --cxl-size=2GiB --integrity-allocation-mode=CxlOnly"
            # configuration_params="--use-integrity-verifier --dram-size=256MiB --dram-os-size=256MiB --cxl-mode=PCIe --cxl-size=2GiB --integrity-allocation-mode=CxlOnly"
            configuration_params = "--use-integrity-verifier --dram-size=256MiB --dram-os-size=256MiB --cxl-mode=DRAM --cxl-size=2GiB --integrity-allocation-mode=CxlOnly"
        case "app-dram":
            # configuration_params="--dram-size=3GiB --cxl-size=0"
            configuration_params = "--dram-size=3GiB"
        case "app-cxl":
            # configuration_params="--enable-cxl --dram-size=256MiB --dram-os-size=256MiB --little-dram --cxl-size=2GiB"
            # configuration_params="--dram-size=256MiB --dram-os-size=256MiB --cxl-mode=PCIe --cxl-size=2GiB"
            configuration_params = "--dram-size=256MiB --dram-os-size=256MiB --cxl-mode=DRAM --cxl-size=2GiB"
        case _:
            print(f"Unknown configuration '{configuration}'")
            exit(1)

    outdir = f"output/{args.test_group}/{benchmark}_{configuration}"

    if "integrity-" not in configuration:
        # This configuration must have no integrity capability. Nullify the integrity-related parameters.
        tree_type = None

        # No page swap parameters as well.
        page_swap = None

    if tree_type is not None:
        tree_type_param = f"--integrity-tree-type={tree_type}"
        outdir += f"_{tree_type}"
    else:
        tree_type_param = ""

    match tree_type:
        case "TimingTree":
            tree_type_param += " --integrity-tree-arity=4"
        case "TimingBmt":
            tree_type_param += " --integrity-tree-arity=8"

    if "integrity-" not in configuration:
        # This configuration must have no integrity capability. Nullify the integrity-related parameters.
        metadata_cache_type = None

    if metadata_cache_type is not None:
        metadata_cache_type_param = (
            f"--metadata-cache-type={metadata_cache_type}"
        )
        outdir += f"_{metadata_cache_type}"
    else:
        metadata_cache_type_param = ""

    match metadata_cache_type:
        case "MetadataCache":
            # 2048 * 3
            metadata_cache_type_param += " --metadata-cache-size=6144"
        case "PartitionedMetadataCache":
            metadata_cache_type_param += " --metadata-cache-size-tree-nodes=2048 --metadata-cache-size-counter-nodes=2048 --metadata-cache-size-mac-nodes=2048"
        case _:
            pass

    if page_swap is not None:
        outdir += f"_PageSwap{page_swap}"
    else:
        page_swap_type_param = ""

    match page_swap:
        case "No":
            page_swap_type_param = ""
        case "Yes":
            page_swap_type_param = "--use-ncx --use-page-swapper"
        case _:
            pass

    if "cxl" not in configuration:
        # CXL latency does not apply if CXL is not used.
        cxl_latency = None

    if cxl_latency is not None:
        outdir += f"_CxlLat{cxl_latency}"
        configuration_params += f" --cxl-latency={cxl_latency}"

    try:
        os.makedirs(outdir, exist_ok=True)
        # print(f"Directory '{outdir}' created successfully.")
    except Exception as e:
        print(f"An error occurred while creating '{outdir}': {e}")

    command = f"{gem5_binary} {gem5_params} --outdir {outdir} {config_file} {benchmark_params} {common_config_params} {configuration_params} {tree_type_param} {metadata_cache_type_param} {page_swap_type_param}"

    return command


def handle_signal(signal, frame):
    print("Signal received, terminating all processes...")
    for process in processes:
        process.terminate()  # Terminate each process
    exit(0)  # Exit the script


# Worker function to process commands from the queue
def worker(cmd_queue):
    while True:
        cmd = cmd_queue.get()
        if cmd is None:  # Exit signal
            break
        run_command(cmd)
        cmd_queue.task_done()
        print(f"Approximately {cmd_queue.qsize()} runs left.")


# Function to run a single command
def run_command(cmd):
    try:
        print(f"-> Running command: {cmd}")

        def extract_parameter(command, param_name):
            # Create a regex pattern to find the parameter
            pattern = rf"--{param_name}\s+(\S+)"
            match = re.search(pattern, command)
            if match:
                return match.group(1)  # Return the value of the parameter
            return None  # Return None if the parameter is not found

        outdir = extract_parameter(cmd, "outdir")
        stdout_file = os.path.join(outdir, "output.txt")
        stderr_file = os.path.join(outdir, "error.txt")

        with (
            open(stdout_file, "w") as stdout_f,
            open(stderr_file, "w") as stderr_f,
        ):
            process = subprocess.Popen(
                cmd, shell=True, text=True, stdout=stdout_f, stderr=stderr_f
            )
            processes.append(process)
            returncode = process.wait()

        if returncode != 0:
            print(f"==> FAILED: {outdir}")
            error_runs.append(outdir)
        else:
            print(f"==> SUCCESS: {outdir}")

    except subprocess.CalledProcessError as e:
        print(f"Command failed: {cmd}\nError: {e.stderr}")


def run_suite(commands, max_concurrent):
    start_time = time.time()
    cmd_queue = queue.Queue()

    # Start worker threads
    threads = []
    for _ in range(max_concurrent):
        thread = threading.Thread(target=worker, args=(cmd_queue,))
        thread.start()
        threads.append(thread)

    # Add commands to the queue
    for cmd in commands:
        cmd_queue.put(cmd)

    # Wait for all commands to finish
    cmd_queue.join()

    # Stop workers
    for _ in threads:
        cmd_queue.put(None)  # Send exit signal
    for thread in threads:
        thread.join()

    end_time = time.time()
    total_elapsed_time = end_time - start_time
    print(f"Total run time: {total_elapsed_time:.2f} seconds")

    if len(error_runs) > 0:
        print(
            f"It appears there were some failed runs. The following {len(error_runs)} of {total_runs} failed:"
        )
        for r in error_runs:
            print(r)


if __name__ == "__main__":
    # Register signal handler
    signal.signal(signal.SIGINT, handle_signal)

    # Collect command line arguments
    parser = argparse.ArgumentParser(description="Full test suite runner.")
    parser = add_arguments(parser)
    args = parser.parse_args()

    # Generate variations of tests
    commands_to_run = []
    for b in args.benchmark:
        for c in args.configuration:
            for t in args.tree_type:
                for cache in args.cache_type:
                    for p in args.page_swap:
                        for l in args.cxl_latency:
                            command = compile_command(
                                args,
                                benchmark=b,
                                configuration=c,
                                tree_type=t,
                                metadata_cache_type=cache,
                                page_swap=p,
                                cxl_latency=l,
                            )
                            commands_to_run.append(command)
                            total_runs += 1

    # Set the maximum number of concurrent commands
    max_concurrent_commands = 5

    # print(commands_to_run)
    # exit(0)

    # Remove duplicates
    commands_to_run = list(set(commands_to_run))

    run_suite(commands_to_run, max_concurrent_commands)
