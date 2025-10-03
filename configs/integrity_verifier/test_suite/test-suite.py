#!/usr/bin/env python3


import argparse
import datetime
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time

processes = []

total_runs = 0
error_runs = []
suite_output_file = ""
failed_run_file = ""


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

parsec_sizes = [
    "test",
    "simdev",
    "simsmall",
    "simmedium",
    "simlarge",
    "native",
]

spec2017_benchmarks = [
    # SPECrate
    "500.perlbench_r",
    "502.gcc_r",
    "503.bwaves_r",
    "505.mcf_r",
    "507.cactuBSSN_r",
    "508.namd_r",
    "510.parest_r",
    "511.povray_r",
    "519.lbm_r",
    "520.omnetpp_r",
    "521.wrf_r",
    "523.xalancbmk_r",
    "525.x264_r",
    "526.blender_r",
    "527.cam4_r",
    "531.deepsjeng_r",
    "538.imagick_r",
    "541.leela_r",
    "544.nab_r",
    "548.exchange2_r",
    "549.fotonik3d_r",
    "554.roms_r",
    "557.xz_r",
    # SPECspeed
    "600.perlbench_s",
    "602.gcc_s",
    "603.bwaves_s",
    "605.mcf_s",
    "607.cactuBSSN_s",
    "619.lbm_s",
    "620.omnetpp_s",
    "621.wrf_s",
    "623.xalancbmk_s",
    "625.x264_s",
    "627.cam4_s",
    "628.pop2_s",
    "631.deepsjeng_s",
    "638.imagick_s",
    "641.leela_s",
    "644.nab_s",
    "648.exchange2_s",
    "649.fotonik3d_s",
    "654.roms_s",
    "657.xz_s",
    # SPECrand
    "996.specrand_fs",
    "997.specrand_fr",
    "998.specrand_is",
    "999.specrand_ir",
]

spec2017_sizes = [
    "test",
    "train",
    "ref",
]

ycsb_db_names = [
    "memcached",
]

ycsb_workloads = [
    "workloada",
    "workloadb",
    "workloadc",
    "workloadd",
    "workloade",
    "workloadf",
]


def add_arguments(parser):
    parser.add_argument(
        "--threads",
        type=int,
        default=5,
        required=False,
        help="Number of concurrent benchmarks to run at once.",
    )

    parser.add_argument(
        "--test-group",
        type=str,
        required=True,
        help="Group to place all tests into. All tests will be placed into 'output/<test-group>'.",
    )

    parser.add_argument(
        "--retry-file",
        type=str,
        required=False,
        help="File to read from for commands, rather than generating the command list. File should be located in 'output/<test-group>' (Example: failed_runs-2025-09-05_17-58-58.txt)",
    )

    parser.add_argument(
        "--gem5",
        type=str,
        # Only required if --retry-file is not used
        required="--retry-file" not in sys.argv,
        choices=[
            "fast",
            "opt",
            "debug",
        ],
    )

    parser.add_argument(
        "--benchmark",
        type=str,
        # Only required if --retry-file is not used
        required="--retry-file" not in sys.argv,
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
        help="Benchmark(s) to use. The following are accepted: demo-demo, micro-<microbenchmark>, parsec-<benchmark>[-size], spec2017-<benchmark>[-size], ycsb-memcached-<benchmark>",
    )

    parser.add_argument(
        "--configuration",
        type=str,
        # Only required if --retry-file is not used
        required="--retry-file" not in sys.argv,
        nargs="+",
        choices=[
            "app-dram-integrity-dram",
            "app-dram-integrity-cxl",
            "app-cxl-integrity-dram",
            "app-cxl-integrity-cxl",
            "app-dram-only",
            "app-cxl-only",
        ],
        help="System configuration to use.",
    )

    parser.add_argument(
        "--cxl-latency",
        type=str,
        required=False,
        nargs="+",
        help="Manual added latency for CXL memory (latency added twice, for request and response).",
    )

    parser.add_argument(
        "--cxl-memory-type",
        type=str,
        required=False,
        nargs="+",
        choices=[
            "DRAM",
            "Flash",
        ],
    )

    parser.add_argument(
        "--tree-type",
        type=str,
        required=False,
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
        required=False,
        nargs="+",
        choices=[
            "MetadataCache",
            "PartitionedMetadataCache",
            "None",
        ],
    )

    # If partitioned metadata cache is used, this size applies
    # to EACH partition
    parser.add_argument(
        "--metadata-cache-size",
        type=int,
        required=False,
        nargs="+",
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
        "--page-swap-epoch",
        type=int,
        required=False,
        nargs="+",
    )

    parser.add_argument(
        "--debug-flags",
        type=str,
        required=False,
        help="Same as --debug-flags parameter used in gem5. Write flags in comma-separated list. Passed to all test variations.",
    )

    parser.add_argument(
        "--extra-arguments",
        type=str,
        default="",
        required=False,
        help="Extra parameters to pass to the simulation. Passed to all test variations.",
    )

    parser.add_argument(
        "--print-configs",
        action="store_true",
        help="Rather than running the test suite, simply print out all the configs that would run.",
    )

    return parser


# Parse configuration details and create a gem5 command to run.
def compile_command(
    args,
    benchmark: str,
    configuration: str,
    tree_type: str = None,
    metadata_cache_type: str = None,
    metadata_cache_size: int = None,
    page_swap: str = None,
    page_swap_epoch: int = None,
    cxl_latency: str = None,
    cxl_memory_type: str = None,
    extra_arguments: str = "",
):
    match args.gem5:
        case "fast":
            gem5_binary = "./build/X86/gem5.fast"
        case "opt":
            gem5_binary = "./build/X86/gem5.opt"
        case "debug":
            gem5_binary = "./build/X86/gem5.debug"
        case _:
            print(f"Unknown gem5 type '{args.gem5}'")
            exit(1)

    gem5_params = "--listener-mode=on --silent-redirect --redirect-stdout --stdout-file='output.txt' --redirect-stderr --stderr-file='error.txt'"
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
    elif "spec2017-" in benchmark:
        # This must be a SPEC CPU 2017 benchmark.
        config_file = "configs/integrity_verifier/x86-spec2017-ubuntu-22.py"
        resource_build_path = f"{custom_img_path}/build-spec2017-22-04"
        # kernel_path = f"{resource_build_path}/vmlinux-x86-ubuntu"
        kernel_path = (
            f"{resource_build_path}/vmlinux-5.15.0-141-generic+cxldmsim"
        )
        img_path = f"{resource_build_path}/spec2017-22-04"
    elif "ycsb-memcached-" in benchmark:
        # This must be a YCSB benchmark.
        config_file = "configs/integrity_verifier/x86-ycsb-ubuntu-22.py"
        resource_build_path = f"{custom_img_path}/build-ycsb-22-04"
        kernel_path = f"{resource_build_path}/vmlinux-x86-ubuntu"
        img_path = f"{resource_build_path}/ycsb-22-04"
    elif "trace-" in benchmark:
        # This must be a trace run.
        config_file = "configs/integrity_verifier/x86-tracerun-ubuntu-22.py"
        resource_build_path = f"{custom_img_path}/build-microbenchmarks-22-04"
        kernel_path = f"{resource_build_path}/vmlinux-x86-ubuntu"
        img_path = f"{resource_build_path}/microbenchmarks-22-04"
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
        case str(x) if "parsec-" in x:
            split_string = benchmark.split("-")
            benchmark_name = split_string[1]
            assert benchmark_name in parsec_benchmarks
            size = split_string[2] if len(split_string) >= 3 else "simmedium"
            assert size in parsec_sizes
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"

        # SPEC CPU 2017
        case str(x) if "spec2017-" in x:
            split_string = benchmark.split("-")
            benchmark_name = split_string[1]
            assert benchmark_name in spec2017_benchmarks
            size = split_string[2] if len(split_string) >= 3 else "ref"
            assert size in spec2017_sizes
            benchmark_params = f"--benchmark {benchmark_name} --size {size} --kernel-path {kernel_path} --img-path {img_path}"

        case str(x) if "ycsb-" in x:
            split_string = benchmark.split("-")
            db_name = split_string[1]
            assert db_name in ycsb_db_names
            workload_name = split_string[2]
            assert workload_name in ycsb_workloads
            benchmark_params = f"--database-type {db_name} --workload {workload_name} --record-count 100000 --operation-count 100000 --kernel-path {kernel_path} --img-path {img_path}"

        case str(x) if "trace-" in x:
            split_string = benchmark.split("-")
            trace_name = split_string[1]
            # assert db_name in ycsb_db_names
            # workload_name = split_string[2]
            # assert workload_name in ycsb_workloads
            benchmark_params = f"--trace {trace_name} --kernel-path {kernel_path} --img-path {img_path}"

        case _:
            print(f"Unknown benchmark '{benchmark}'")
            exit(1)

    common_config_params = ""
    match configuration:
        case "app-dram-integrity-dram":
            # configuration_params = "--use-integrity-verifier --dram-size=3GiB --integrity-allocation-mode=DramOnly"
            configuration_params = "--use-integrity-verifier --dram-size=16GiB --cxl-mode=DRAM --cxl-size=16GiB --integrity-allocation-mode=DramOnly --app-on-device=DRAM"
        case "app-dram-integrity-cxl":
            # configuration_params = "--use-integrity-verifier --dram-size=3GiB --cxl-mode=DRAM --cxl-size=2GiB --integrity-allocation-mode=CxlOnly --no-apps-on-secondary-memory"
            configuration_params = "--use-integrity-verifier --dram-size=16GiB --cxl-mode=DRAM --cxl-size=16GiB --integrity-allocation-mode=CxlOnly --app-on-device=DRAM"
        case "app-cxl-integrity-dram":
            # configuration_params = "--use-integrity-verifier --dram-size=3GiB --dram-os-size=256MiB --cxl-mode=DRAM --cxl-size=2GiB --integrity-allocation-mode=DramOnly"
            configuration_params = "--use-integrity-verifier --dram-size=16GiB --cxl-mode=DRAM --cxl-size=16GiB --integrity-allocation-mode=DramOnly --app-on-device=CXL"
        case "app-cxl-integrity-cxl":
            # configuration_params = "--use-integrity-verifier --dram-size=256MiB --dram-os-size=256MiB --cxl-mode=DRAM --cxl-size=2GiB --integrity-allocation-mode=CxlOnly"
            configuration_params = "--use-integrity-verifier --dram-size=16GiB --cxl-mode=DRAM --cxl-size=16GiB --integrity-allocation-mode=CxlOnly --app-on-device=CXL"
        case "app-dram-only":
            # configuration_params = "--dram-size=3GiB"
            configuration_params = "--dram-size=16GiB --cxl-mode=DRAM --cxl-size=16GiB --app-on-device=DRAM"
        case "app-cxl-only":
            # configuration_params = "--dram-size=256MiB --dram-os-size=256MiB --cxl-mode=DRAM --cxl-size=2GiB"
            configuration_params = "--dram-size=16GiB --cxl-mode=DRAM --cxl-size=16GiB --app-on-device=CXL"
        case _:
            print(f"Unknown configuration '{configuration}'")
            exit(1)

    if "cxl" in configuration and cxl_memory_type is not None:
        configuration_params += f" --cxl-memory-type={cxl_memory_type}"

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
            if metadata_cache_size is None:
                # 2048 * 3
                metadata_cache_size = 6144
            else:
                outdir += f"{metadata_cache_size}"
            metadata_cache_type_param += (
                f" --metadata-cache-size={metadata_cache_size}"
            )
        case "PartitionedMetadataCache":
            if metadata_cache_size is None:
                metadata_cache_size = 2048
            else:
                outdir += f"{metadata_cache_size}"
            metadata_cache_type_param += f" --metadata-cache-size-tree-nodes={metadata_cache_size} --metadata-cache-size-counter-nodes={metadata_cache_size} --metadata-cache-size-mac-nodes={metadata_cache_size}"
        case "None":
            pass
        case _:
            if metadata_cache_size is not None:
                outdir += f"_MetadataCacheSize{metadata_cache_size}"
                metadata_cache_type_param += f" --metadata-cache-size={metadata_cache_size} --metadata-cache-size-tree-nodes={metadata_cache_size} --metadata-cache-size-counter-nodes={metadata_cache_size} --metadata-cache-size-mac-nodes={metadata_cache_size}"

    if page_swap is not None:
        outdir += f"_PageSwap{page_swap}"
    else:
        page_swap_type_param = ""

    match page_swap:
        case "No":
            page_swap_type_param = ""
            page_swap_epoch = None
        case "Yes":
            page_swap_type_param = "--use-ncx --use-page-swapper"
        case _:
            pass

    if page_swap_epoch is not None:
        outdir += f"_SwapEpoch{page_swap_epoch}"
        page_swap_type_param += f" --page-swap-epoch={page_swap_epoch}"

    if "cxl" not in configuration:
        # CXL latency does not apply if CXL is not used.
        cxl_latency = None

    if cxl_latency is not None:
        outdir += f"_CxlLat{cxl_latency}"
        configuration_params += f" --cxl-latency={cxl_latency}"

    command = f"{gem5_binary} {gem5_params} --outdir {outdir} {config_file} {benchmark_params} {common_config_params} {configuration_params} {tree_type_param} {metadata_cache_type_param} {page_swap_type_param} {extra_arguments}"

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
        print(
            f"-> [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running command: {cmd}"
        )

        def extract_parameter(command, param_name):
            # Create a regex pattern to find the parameter
            pattern = rf"--{param_name}\s+(\S+)"
            match = re.search(pattern, command)
            if match:
                return match.group(1)  # Return the value of the parameter
            return None  # Return None if the parameter is not found

        outdir = extract_parameter(cmd, "outdir")
        try:
            os.makedirs(outdir, exist_ok=True)
            # print(f"Directory '{outdir}' created successfully.")
        except Exception as e:
            print(f"An error occurred while creating '{outdir}': {e}")

        stdout_file = os.path.join(outdir, "output_wrapper.txt")
        stderr_file = os.path.join(outdir, "error_wrapper.txt")

        cmd_start = time.time()

        with (
            open(stdout_file, "w") as stdout_f,
            open(stderr_file, "w") as stderr_f,
        ):
            process = subprocess.Popen(
                cmd, shell=True, text=True, stdout=stdout_f, stderr=stderr_f
            )
            processes.append(process)
            returncode = (
                process.wait()
            )  # Consider adding timeout in seconds here. This causes a TimeoutExpired exception.

        cmd_end = time.time()
        total_elapsed_time = cmd_end - cmd_start

        # Double check things work the way they were supposed to. Read through the simulation
        # output and check to see if there was a kernel panic, or other issue that
        # invalidates the test.
        #
        # These messages selected are just based from experience on what has been output during
        # an issue.
        try:
            with open(outdir + "/board.pc.com_1.device") as f:
                for line in f:
                    if any(
                        s in line
                        for s in [
                            "BUG: unable to handle page fault",
                            "kernel BUG at",
                            "] RIP: ",
                            "segfault",
                            "BUG: Bad rss-counter state",
                            # "] ata1.00: failed command: READ DMA", # May also be concerning
                        ]
                    ):
                        # This should be considered an issue.
                        # We will simply mock this by tweaking the return code variable.
                        returncode = 1
                        break
        except FileNotFoundError:
            # No output is equally an issue.
            returncode = 1

        if returncode != 0:
            print(
                f"==> [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] FAILED: {outdir} (duration: {total_elapsed_time/60:.2f} minutes)"
            )
            with open(suite_output_file, "a") as f:
                f.write(
                    f"==> [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] FAILED: {outdir} (duration: {total_elapsed_time/60:.2f} minutes)\n"
                )
            error_runs.append(
                {
                    "dir": outdir,
                    "cmd": cmd,
                }
            )
        else:
            print(
                f"==> [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SUCCESS: {outdir} (duration: {total_elapsed_time/60:.2f} minutes)"
            )
            with open(suite_output_file, "a") as f:
                f.write(
                    f"==> [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SUCCESS: {outdir} (duration: {total_elapsed_time/60:.2f} minutes)\n"
                )

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
    print(
        f"Total run time: {(total_elapsed_time / 3600):.2f}hr / {(total_elapsed_time / 60):.2f}min / {total_elapsed_time:.2f}s"
    )

    with open(suite_output_file, "a") as f:
        f.write(
            f"Total run time: {(total_elapsed_time / 3600):.2f}hr / {(total_elapsed_time / 60):.2f}min / {total_elapsed_time:.2f}s\n"
        )

    if len(error_runs) > 0:
        print(
            f"It appears there were some failed runs. The following {len(error_runs)} of {total_runs} failed:"
        )
        for r in error_runs:
            print(r["dir"])

        # Output to file
        with open(suite_output_file, "a") as f:
            f.write("-------\n")
            f.write(f"Failed runs ({len(error_runs)} total):\n")
            for r in error_runs:
                f.write(r["dir"])
                f.write("\n")

        with open(failed_run_file, "w") as f:
            for r in error_runs:
                f.write(r["cmd"])
                f.write("\n")


if __name__ == "__main__":
    # Register signal handler
    signal.signal(signal.SIGINT, handle_signal)

    # Collect command line arguments
    parser = argparse.ArgumentParser(
        description="Full test suite runner. Specify multiple of each flag to run tests for multiple variations."
    )
    parser = add_arguments(parser)
    args = parser.parse_args()

    suite_output_file = f'output/{args.test_group}/suite_output-{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}{"-dryrun" if args.print_configs else ""}.txt'
    failed_run_file = f"output/{args.test_group}/failed_runs-{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"

    try:
        os.makedirs(f"output/{args.test_group}", exist_ok=True)
        # print(f"Directory '{outdir}' created successfully.")
    except Exception as e:
        print(
            f"An error occurred while creating 'output/{args.test_group}': {e}"
        )

    # parsec-blackscholes-test parsec-bodytrack-test parsec-canneal-test parsec-dedup-test parsec-facesim-test parsec-ferret-test parsec-fluidanimate-test parsec-freqmine-test parsec-raytrace-test parsec-streamcluster-test parsec-swaptions-test parsec-vips-test parsec-x264-test
    # parsec-blackscholes-simsmall parsec-bodytrack-simsmall parsec-canneal-simsmall parsec-dedup-simsmall parsec-facesim-simsmall parsec-ferret-simsmall parsec-fluidanimate-simsmall parsec-freqmine-simsmall parsec-raytrace-simsmall parsec-streamcluster-simsmall parsec-swaptions-simsmall parsec-vips-simsmall parsec-x264-simsmall

    # for benchmark in args.benchmark:
    #     if "parsec-_" in benchmark:
    #         args.benchmark.

    benchmarks = args.benchmark or [None]
    configurations = args.configuration or [None]
    tree_types = args.tree_type or [None]
    cache_types = args.cache_type or [None]
    metadata_cache_sizes = args.metadata_cache_size or [None]
    page_swap_types = args.page_swap or [None]
    page_swap_epochs = args.page_swap_epoch or [None]
    cxl_latencies = args.cxl_latency or [None]
    cxl_memory_types = args.cxl_memory_type or [None]

    # Generate variations of tests
    commands_to_run = []

    if args.retry_file:
        retry_file = f"output/{args.test_group}/{args.retry_file}"
        print(f"Using retry file '{args.retry_file}'")

        commands_to_run = []
        with open(retry_file) as f:
            lines = f.readlines()
            for line in lines:
                line = line.strip()
                if line is not None and line != "":
                    commands_to_run.append(line)

    else:
        # No retry file; compute commands now
        for b in benchmarks:
            for c in configurations:
                for t in tree_types:
                    for cache in cache_types:
                        for metadata_cache_size in metadata_cache_sizes:
                            for p in page_swap_types:
                                for epoch in page_swap_epochs:
                                    for l in cxl_latencies:
                                        for cmt in cxl_memory_types:
                                            command = compile_command(
                                                args,
                                                benchmark=b,
                                                configuration=c,
                                                tree_type=t,
                                                metadata_cache_type=cache,
                                                metadata_cache_size=metadata_cache_size,
                                                page_swap=p,
                                                page_swap_epoch=epoch,
                                                cxl_latency=l,
                                                cxl_memory_type=cmt,
                                                extra_arguments=args.extra_arguments,
                                            )
                                            commands_to_run.append(command)

    # Set the maximum number of concurrent commands
    max_concurrent_commands = args.threads

    # Remove duplicates
    commands_to_run = list(set(commands_to_run))
    total_runs = len(commands_to_run)

    with open(suite_output_file, "w") as f:
        f.write("==================================================\n")
        f.write(
            f"Test Suite Run on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        f.write("Launch Command: ")
        f.write(" ".join(sys.argv[:]))
        f.write("\n")
        f.write("-------\n")
        f.write(f"Commands to run ({len(commands_to_run)} total):\n")
        for command in commands_to_run:
            f.write(command)
            f.write("\n")
        f.write("-------\n")
        f.write("Starting.\n")
        f.write("-------\n")

    if args.print_configs:
        print(f"Commands ({len(commands_to_run)} total): ")
        for command in commands_to_run:
            print(f"--> {command}")
        exit(0)

    run_suite(commands_to_run, max_concurrent_commands)

    with open(suite_output_file, "a") as f:
        f.write("-------\n")
        f.write(
            f"Complete at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        f.write("==================================================\n")
