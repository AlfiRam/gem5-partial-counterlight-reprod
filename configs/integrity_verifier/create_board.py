# Generate a common board configuration across workloads. This also provides
# some additional relevant arguments.

import sys

from m5.objects import (
    BadAddr,
    GlobalInstTracker,
    LocalInstTracker,
    SystemXBar,
)
from m5.util import warn
from m5.util.convert import toMemorySize

from gem5.components.boards.x86_board import X86Board
from gem5.components.cachehierarchies.classic.no_cache import NoCache
from gem5.components.cachehierarchies.classic.private_l1_private_l2_shared_l3_cache_hierarchy import (
    PrivateL1PrivateL2SharedL3CacheHierarchy,
)
from gem5.components.cachehierarchies.classic.private_l1_private_l2_shared_l3_cache_hierarchy_integrity_verifier import (
    PrivateL1PrivateL2SharedL3CacheHierarchyIntegrityVerifier,
)
from gem5.components.memory.mtree.TimingBmt import TimingBmt
from gem5.components.memory.mtree.TimingTree import TimingTree
from gem5.components.memory.single_channel import DIMM_DDR5_4400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.processors.simple_switchable_processor import (
    SimpleSwitchableProcessor,
)
from gem5.isas import ISA
from gem5.utils.requires import requires


def add_arguments(parser):
    # CPU Configuration
    parser.add_argument(
        "--cores",
        type=int,
        required=False,
        help="Number of CPU cores to simulate.",
        default=2,
    )

    parser.add_argument(
        "--inst-tracking",
        action="store_true",
        required=False,
        help="Add instruction tracking functionality.",
    )

    parser.add_argument(
        "--ff-insts",
        type=int,
        required="--inst-tracking" in sys.argv,
        help="Specify number of instructions to fast-forward. This may have issues if the workload is shorter than the number of instructions specified. Only applies if --inst-tracking is used.",
        default=1_000_000_000,
    )

    parser.add_argument(
        "--exec-insts",
        type=int,
        required="--inst-tracking" in sys.argv,
        help="Specify number of instructions to execute. This may have issues if the workload is shorter than the number of instructions specified. Only applies if --inst-tracking is used.",
        default=500_000_000,
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        required=False,
        help="Use no cache.",
    )

    parser.add_argument(
        "--unified-l1-cache",
        action="store_true",
        required=False,
        help="Use a unified I/D L1 cache.",
    )

    parser.add_argument(
        "--l2-size",
        type=str,
        required=False,
        help="Size of L2 cache.",
        default="2MiB",
    )

    parser.add_argument(
        "--l2-assoc",
        type=int,
        required=False,
        help="Associativity of L2 cache.",
        default=16,
    )

    parser.add_argument(
        "--l3-size",
        type=str,
        required=False,
        help="Size of L3 cache.",
        default="16MiB",
    )

    parser.add_argument(
        "--l3-assoc",
        type=int,
        required=False,
        help="Associativity of L3 cache.",
        default=32,
    )

    # Memory sizes
    parser.add_argument(
        "--dram-size",
        type=str,
        required=True,
        help="Total size of DRAM.",
        # default="3GiB",
        # default="0B",
    )

    parser.add_argument(
        "--dram-os-size",
        type=str,
        required=False,
        help="Total OS-visible size of DRAM. Overrides any auto-calculated values.",
    )

    parser.add_argument(
        "--cxl-size",
        type=str,
        required=False,
        help="Total size of CXL memory, if enabled. This option does nothing if CXL is not enabled.",
        # default="8GiB",
        default="0B",
    )

    # Integrity verification
    parser.add_argument(
        "--use-integrity-verifier",
        action="store_true",
        help="Add an 'integrity verifier' component to add integrity management behavior.",
    )

    parser.add_argument(
        "--integrity-allocation-mode",
        type=str,
        required=False,
        help="Allocation scheme for integrity data.",
        # default="DramOnly",
        choices=[
            "DramOnly",
            "CxlOnly",
            "BasicMix",
        ],
    )

    parser.add_argument(
        "--integrity-tree-type",
        type=str,
        required=False,
        default="TimingBmt",
        choices=[
            "TimingTree",
            "TimingBmt",
            "None",
        ],
    )

    parser.add_argument(
        "--integrity-tree-arity",
        type=int,
        required=False,
        default=8,
    )

    parser.add_argument(
        "--kvm-only",
        action="store_true",
        help="Use KVM cores exclusively.",
    )

    # Simulation modeling
    parser.add_argument(
        "--timing-from-start",
        action="store_true",
        help="Instead of switching from KVM cores to timing cores when reaching the POI, use timing cores starting at boot.",
    )

    parser.add_argument(
        "--atomic-from-start",
        action="store_true",
        help="Switch from Atomic cores to timing cores when reaching the POI.",
    )

    # Integrity metadata cache
    parser.add_argument(
        "--metadata-cache-type",
        type=str,
        required=False,
        default="PartitionedMetadataCache",
        choices=[
            "MetadataCache",
            "PartitionedMetadataCache",
        ],
    )

    parser.add_argument(
        "--metadata-cache-size",
        type=int,
        required=False,
        help="Number of entries in the (unified) metadata cache, if applicable.",
        default=2048,
    )

    parser.add_argument(
        "--metadata-cache-size-tree-nodes",
        type=int,
        required=False,
        help="Number of tree node entries in the (split) metadata cache, if applicable.",
        default=2048,
    )

    parser.add_argument(
        "--metadata-cache-size-counter-nodes",
        type=int,
        required=False,
        help="Number of counter node entries in the (split) metadata cache, if applicable.",
        default=2048,
    )

    parser.add_argument(
        "--metadata-cache-size-mac-nodes",
        type=int,
        required=False,
        help="Number of MAC node entries in the (split) metadata cache, if applicable.",
        default=2048,
    )

    parser.add_argument(
        "--metadata-cache-assoc",
        type=int,
        required=False,
        help="Associativity of metadata cache.",
        default=16,
    )

    parser.add_argument(
        "--unified-upstream-cache",
        action="store_true",
        required=False,
        help="Enable using the LLC as a metadata cache.",
    )

    # CXL configuration
    parser.add_argument(
        "--cxl-mode",
        type=str,
        help="Enable CXL memory.",
        default="Disabled",
        choices=[
            "Disabled",
            "PCIe",
            "DRAM",
        ],
    )

    parser.add_argument(
        "--cxl-memory-type",
        type=str,
        help="Set CXL memory type. For CXL on DRAM mode only.",
        default="DRAM",
        choices=[
            "DRAM",
            "Flash",
        ],
    )

    parser.add_argument(
        "--cxl-latency",
        type=str,
        help="Custom CXL latency (per direction). For CXL on DRAM mode only.",
        # default="35ns"
        default="55ns",
    )

    parser.add_argument(
        "--cxl-latency-read-req",
        type=str,
        help="Custom CXL latency (read requests). For CXL on DRAM mode only. Overrides CXL latency.",
    )

    parser.add_argument(
        "--cxl-latency-read-resp",
        type=str,
        help="Custom CXL latency (read responses). For CXL on DRAM mode only. Overrides CXL latency.",
    )

    parser.add_argument(
        "--cxl-latency-write-req",
        type=str,
        help="Custom CXL latency (write requests). For CXL on DRAM mode only. Overrides CXL latency.",
    )

    parser.add_argument(
        "--cxl-latency-write-resp",
        type=str,
        help="Custom CXL latency (write responses). For CXL on DRAM mode only. Overrides CXL latency.",
    )

    parser.add_argument(
        "--is-asic",
        action="store_true",
        help="Choose to simulate CXL ASIC Device (if true) or FPGA Device (if false). This option does nothing if CXL is not enabled.",
    )

    parser.add_argument(
        "--main-memory-type",
        type=str,
        help="Type of memory that is used as primary memory. (Starting at address 0.)",
        default="DRAM",
        choices=[
            "DRAM",
            "CXL",
        ],
    )

    parser.add_argument(
        "--no-apps-on-secondary-memory",
        action="store_true",
        help="Disable the use of secondary memory for application/OS data. (Use it for integrity data only.) The secondary memory type is based on --main-memory-type.",
    )

    # Page swapping
    parser.add_argument(
        "--use-page-swapper",
        action="store_true",
        help="Add a 'page swapper' component. Requires an integrity verifier.",
    )

    parser.add_argument(
        "--page-swap-epoch",
        type=int,
        default=200,
        help="Number of requests between page swap attempts.",
    )

    parser.add_argument(
        "--use-ncx",
        action="store_true",
        help="Use noncoherent xbar structure.",
    )

    return parser


def create_board(args):
    # This simulation requires X86 simulation
    requires(
        isa_required=ISA.X86,
    )

    # This is where extra specialized variables can be
    # passed out from this function to the config being used.
    extras = {}

    # Sanity checking parameters.
    # TODO
    if args.cxl_mode == "Disabled":
        # You cannot have a non-zero CXL size when not using CXL.
        assert args.cxl_size == "0B"

    if args.use_page_swapper:
        assert args.use_integrity_verifier

    # Assume wherever the OS is, there is some space available for it
    baseline_os_size = "256MiB"

    tree_classes = {
        "TimingTree": TimingTree,
        "TimingBmt": TimingBmt,
    }

    if args.use_integrity_verifier:
        # Consider "local" memory the memory that may have a variable
        # OS-visible size. This is the memory that integrity data is stored
        # on, so the exact size visible to the OS depends on the tree size.
        # "Remote" memory is the memory that has a statically-sized
        # OS-visible size. Integrity data is not stored here, so the size is
        # not changed no matter the tree size.

        integrity_on_main_memory = (
            args.integrity_allocation_mode == "DramOnly"
            and args.main_memory_type == "DRAM"
        ) or (
            args.integrity_allocation_mode == "CxlOnly"
            and args.main_memory_type == "CXL"
        )

        match args.main_memory_type:
            case "DRAM":
                primary_memory_size = args.dram_size
                # Create override if needed.
                primary_memory_os_size = args.dram_os_size
                secondary_memory_size = args.cxl_size

            case "CXL":
                primary_memory_size = args.cxl_size
                # No override.
                primary_memory_os_size = None
                secondary_memory_size = (
                    args.dram_size
                    if not args.dram_os_size
                    else args.dram_os_size
                )

            case _:
                pass

        if integrity_on_main_memory:
            # Main memory will always have a minimum size.
            min_variable_memory = (
                baseline_os_size
                if primary_memory_os_size is None
                else primary_memory_os_size
            )
            # If needed, force a certain "OS size" for local memory (overrides max) -- 0 means to fallback to total memory size.
            max_variable_memory = (
                "0B"
                if primary_memory_os_size is None
                else primary_memory_os_size
            )
            total_variable_memory_size = primary_memory_size
            # If secondary memory should not be used by apps, do not consider its size.
            total_static_memory_size = (
                secondary_memory_size
                if not args.no_apps_on_secondary_memory
                else "0B"
            )
        else:
            # If secondary memory should not be used by apps, there are no minimum limits to its OS-visible size.
            min_variable_memory = (
                baseline_os_size
                if not args.no_apps_on_secondary_memory
                else "0B"
            )
            max_variable_memory = "0B"
            total_variable_memory_size = secondary_memory_size
            total_static_memory_size = primary_memory_size

        tree_class = tree_classes[args.integrity_tree_type]

        variable_os_size, static_os_size = (
            tree_class.determine_max_protected_size(
                min_local_size=toMemorySize(min_variable_memory),
                max_local_size=toMemorySize(max_variable_memory),
                total_local_size=toMemorySize(total_variable_memory_size),
                total_remote_size=toMemorySize(total_static_memory_size),
                arity=args.integrity_tree_arity,
            )
        )

        match args.integrity_allocation_mode:
            case "DramOnly":
                dram_os_size = variable_os_size
                cxl_os_size = static_os_size
            case "CxlOnly":
                dram_os_size = static_os_size
                cxl_os_size = variable_os_size
            case _:
                pass
    else:
        dram_os_size = toMemorySize(args.dram_size)
        cxl_os_size = toMemorySize(args.cxl_size)

    print(f"Computed DRAM OS Size: {dram_os_size}")
    print(f"Computed CXL OS Size: {cxl_os_size}")

    # Override if necessary.
    if args.dram_os_size:
        dram_os_size = toMemorySize(args.dram_os_size)
        print(f"Overriding DRAM OS Size to {dram_os_size}")

    # DRAM
    if toMemorySize(args.dram_size) > 0:
        memory = []

        if toMemorySize(args.dram_size) <= toMemorySize("3GiB"):
            # Memory can fit within one memory controller.
            memory.append(
                DIMM_DDR5_4400(size=args.dram_size, os_size=f"{dram_os_size}B")
            )
        else:
            warn(
                f"Physical memory size specified is {args.dram_size} which "
                "is greater than 3GiB. Twice the number of memory "
                "controllers will be created."
            )
            # Create the first 3 GiB
            if dram_os_size <= toMemorySize("3GiB"):
                first_dram_os_size = dram_os_size
                remaining_dram_os_size = 0
            else:
                first_dram_os_size = toMemorySize("3GiB")
                remaining_dram_os_size = dram_os_size - toMemorySize("3GiB")
            memory.append(
                DIMM_DDR5_4400(size="3GiB", os_size=f"{first_dram_os_size}B")
            )

            # Create the remaining space
            remaining_dram_size = toMemorySize(args.dram_size) - toMemorySize(
                "3GiB"
            )
            memory.append(
                DIMM_DDR5_4400(
                    size=f"{remaining_dram_size}B",
                    os_size=f"{remaining_dram_os_size}B",
                )
            )
    else:
        memory = []

    cxl_latency_read_req = args.cxl_latency_read_req
    cxl_latency_read_resp = args.cxl_latency_read_resp
    cxl_latency_write_req = args.cxl_latency_write_req
    cxl_latency_write_resp = args.cxl_latency_write_resp

    # CXL memory
    if args.cxl_mode != "Disabled" and toMemorySize(args.cxl_size) > 0:
        if args.cxl_memory_type == "DRAM":
            cxl_memory = DIMM_DDR5_4400(
                size=args.cxl_size, os_size=f"{cxl_os_size}B"
            )
        elif args.cxl_memory_type == "Flash":
            # Flash-like memory (much higher latency than DRAM)
            # TODO Should test to make sure these numbers make sense
            # cxl_memory = SingleChannelSimpleMemory(
            #     latency="100ns", # Base latency time, add the time from delay component to this
            #     latency_var="0", # No variation in latency needed
            #     bandwidth="27GiB/s", # CMM-H peak bandwidth from soltaniyeh25
            #     size=args.cxl_size,
            #     os_size=f"{cxl_os_size}B"
            # )
            # # Reads add 350ns. Divide by 2 to split both ways
            # cxl_latency_read_req = "175ns"
            # cxl_latency_read_resp = "175ns"
            # # Writes add 500ns. Divide by 2 to split both ways
            # cxl_latency_write_req = "250ns"
            # cxl_latency_write_resp = "250ns"

            # Broken so trying this for now
            cxl_memory = DIMM_DDR5_4400(
                size=args.cxl_size, os_size=f"{cxl_os_size}B"
            )
            # Reads add 350ns. Divide by 2 to split both ways
            cxl_latency_read_req = "175ns"
            cxl_latency_read_resp = "175ns"
            # Writes add 500ns. Divide by 2 to split both ways
            cxl_latency_write_req = "250ns"
            cxl_latency_write_resp = "250ns"
    else:
        cxl_memory = None

    membus = SystemXBar(width=64)
    membus.badaddr_responder = BadAddr()
    membus.default = membus.badaddr_responder.pio

    # Cache
    if args.use_integrity_verifier:
        cache_hierarchy = PrivateL1PrivateL2SharedL3CacheHierarchyIntegrityVerifier(
            l1d_size="32KiB",
            l1d_assoc=8,
            l1i_size="32KiB",
            l1i_assoc=8,
            l2_size=args.l2_size,
            l2_assoc=args.l2_assoc,
            l3_size=args.l3_size,
            l3_assoc=args.l3_assoc,
            unified_l1_cache=args.unified_l1_cache,
            membus=membus,
            metadata_cache_type=args.metadata_cache_type,
            metadata_cache_size=args.metadata_cache_size,
            metadata_cache_size_tree_nodes=args.metadata_cache_size_tree_nodes,
            metadata_cache_size_counter_nodes=args.metadata_cache_size_counter_nodes,
            metadata_cache_size_mac_nodes=args.metadata_cache_size_mac_nodes,
            metadata_cache_assoc=args.metadata_cache_assoc,
            unified_upstream_cache=args.unified_upstream_cache,
            integrity_allocation_mode=args.integrity_allocation_mode,
            integrity_tree_type=args.integrity_tree_type,
            integrity_tree_arity=args.integrity_tree_arity,
            use_page_swapper=args.use_page_swapper,
            page_swap_epoch=args.page_swap_epoch,
        )
    elif args.no_cache:
        cache_hierarchy = NoCache(
            membus=membus,
        )
    else:
        cache_hierarchy = PrivateL1PrivateL2SharedL3CacheHierarchy(
            l1d_size="32KiB",
            l1d_assoc=8,
            l1i_size="32KiB",
            l1i_assoc=8,
            l2_size=args.l2_size,
            l2_assoc=args.l2_assoc,
            l3_size=args.l3_size,
            l3_assoc=args.l3_assoc,
            unified_l1_cache=args.unified_l1_cache,
            membus=membus,
        )

    if args.timing_from_start:
        # Example of a processor that starts in timing mode, rather than switching to timing after boot.
        processor = SimpleProcessor(
            cpu_type=CPUTypes.TIMING, isa=ISA.X86, num_cores=args.cores
        )
        if args.inst_tracking:
            print(
                "Note: Instruction tracking is enabled, but this does nothing in this configuration."
            )
    elif args.atomic_from_start:
        # Processor that starts in atomic, then goes to timing.
        processor = SimpleSwitchableProcessor(
            starting_core_type=CPUTypes.ATOMIC,
            switch_core_type=CPUTypes.TIMING,
            isa=ISA.X86,
            num_cores=args.cores,
        )
        if args.inst_tracking:
            print(
                "Note: Instruction tracking is enabled, but this does nothing in this configuration."
            )
    else:
        # This is a switchable CPU. We first boot Ubuntu using KVM, then the guest
        # will exit the simulation by calling "m5 exit" (see the `command` variable
        # below, which contains the command to be run in the guest after booting).
        # Upon exiting from the simulation, the Exit Event handler will switch the
        # CPU type (see the ExitEvent.EXIT line below, which contains a map to
        # a function to be called when an exit event happens).
        requires(
            kvm_required=True,
        )
        processor = SimpleSwitchableProcessor(
            starting_core_type=CPUTypes.KVM,
            switch_core_type=CPUTypes.TIMING,
            isa=ISA.X86,
            num_cores=args.cores,
        )
        if args.inst_tracking:
            global_inst_tracker = GlobalInstTracker(
                # a list of thresholds to trigger the event
                # inst_thresholds=[1_000_000],
                inst_thresholds=[],
                # Hack to allow this to work with KVM and
                # SimpleSwitchableProcessor
                use_approximate_exit=True,
            )
            extras["global_inst_tracker"] = global_inst_tracker

            all_trackers = []
            for core in processor._switchable_cores[processor._switch_key]:
                tracker = LocalInstTracker(
                    # We pass in the global instruction tracker to the local one
                    global_inst_tracker=global_inst_tracker,
                    # This parameter tells the tracker to start listening to
                    # instructions from the beginning of the simulation. If
                    # set to False, the tracker will not start listening to
                    # instructions until startListening() is called.
                    start_listening=False,
                )
                all_trackers.append(tracker)
                # we attach the tracker to the core
                core.core.probeListener = tracker
            extras["all_trackers"] = all_trackers

        # Here we tell the KVM CPU (the starting CPU) not to use perf,
        # if this is unneeded.
        if not args.inst_tracking:
            print("Disabling perf for KVM cores.")
            for proc in processor.start:
                proc.core.usePerf = False
        else:
            print(
                "Note: Instruction tracking with KVM cores requires perf to be set up. Assuming perf is working as expected."
            )

    # Here we setup the board. The X86Board allows for Full-System X86 simulations.
    board = X86Board(
        clk_freq="3GHz",
        processor=processor,
        memory=memory,
        cache_hierarchy=cache_hierarchy,
        cxl_mode=args.cxl_mode,
        cxl_memory=cxl_memory,
        is_asic=args.is_asic,
        main_memory_type=args.main_memory_type,
        use_ncx=args.use_ncx,
        cxl_latency=args.cxl_latency,
        cxl_latency_read_req=cxl_latency_read_req,
        cxl_latency_read_resp=cxl_latency_read_resp,
        cxl_latency_write_req=cxl_latency_write_req,
        cxl_latency_write_resp=cxl_latency_write_resp,
    )

    return board, processor, extras
