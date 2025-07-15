# Generate a common board configuration across workloads. This also provides
# some additional relevant arguments.

from m5.objects import (
    BadAddr,
    SystemXBar,
)
from m5.util.convert import toMemorySize

from gem5.components.boards.x86_board import X86Board
from gem5.components.cachehierarchies.classic.private_l1_shared_l2_cache_hierarchy import (
    PrivateL1SharedL2CacheHierarchy,
)
from gem5.components.cachehierarchies.classic.private_l1_shared_l2_cache_hierarchy_integrity_verifier import (
    PrivateL1SharedL2CacheHierarchyIntegrityVerifier,
)
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
    parser.add_argument(
        "--cores",
        type=int,
        required=False,
        help="Number of CPU cores to simulate.",
        default=2,
    )

    parser.add_argument(
        "--dram-size",
        type=str,
        required=False,
        help="Total size of DRAM.",
        default="3GiB",
    )

    parser.add_argument(
        "--cxl-size",
        type=str,
        required=False,
        help="Total size of CXL memory, if enabled. This option does nothing if CXL is not enabled.",
        default="0B",
    )

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
        default="DramOnly",
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
        default="TimingTree",
        choices=[
            "TimingTree",
            "None",
        ],
    )

    parser.add_argument(
        "--integrity-tree-arity",
        type=int,
        required=False,
        default=4,
    )

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

    parser.add_argument(
        "--metadata-cache-size",
        type=int,
        required=False,
        help="Number of entries in the metadata cache, if applicable.",
        default=2048,
    )

    return parser


def create_board(args):
    # This simulation requires using KVM with gem5 compiled for X86 simulation
    requires(
        isa_required=ISA.X86,
    )
    # Assume wherever the OS is, there is some space available for it
    baseline_os_size = "256MiB"

    if args.integrity_allocation_mode == "DramOnly":
        # All integrity data is stored in DRAM.
        # In this case, we consider DRAM "local" and CXL "remote", resizing the
        # "local" size until we can protect both the local and remote space.
        match args.integrity_tree_type:
            case "TimingTree":
                dram_os_size, cxl_os_size = TimingTree.determine_max_protected_size(
                    min_local_size=toMemorySize(baseline_os_size),
                    total_local_size=toMemorySize(args.dram_size),
                    total_remote_size=toMemorySize(args.cxl_size),
                    arity=args.integrity_tree_arity,
                )
            case _:
                print(f"Unknown integrity tree type '{args.integrity_tree_type}'")
                exit(1)
    else:
        print(
            f"Unimplmented integrity allocation mode '{args.integrity_allocation_mode}'"
        )
        exit(1)

    print(f"Computed DRAM OS Size: {dram_os_size}")
    print(f"Computed CXL OS Size: {cxl_os_size}")
    # Main memory
    memory = DIMM_DDR5_4400(size=args.dram_size, os_size=f"{dram_os_size}B")

    membus = SystemXBar(width=64)
    membus.badaddr_responder = BadAddr()
    membus.default = membus.badaddr_responder.pio

    # Cache
    if args.use_integrity_verifier:
        cache_hierarchy = PrivateL1SharedL2CacheHierarchyIntegrityVerifier(
            l1d_size="32KiB",
            l1d_assoc=8,
            l1i_size="32KiB",
            l1i_assoc=8,
            l2_size="512KiB",
            l2_assoc=16,
            membus=membus,
            metadata_cache_size=args.metadata_cache_size,
            integrity_allocation_mode=args.integrity_allocation_mode,
            integrity_tree_type=args.integrity_tree_type,
            integrity_tree_arity=args.integrity_tree_arity,
        )
    else:
        cache_hierarchy = PrivateL1SharedL2CacheHierarchy(
            l1d_size="32KiB",
            l1d_assoc=8,
            l1i_size="32KiB",
            l1i_assoc=8,
            l2_size="512KiB",
            l2_assoc=16,
            membus=membus,
        )

    if args.timing_from_start:
        # Example of a processor that starts in timing mode, rather than switching to timing after boot.
        processor = SimpleProcessor(
            cpu_type=CPUTypes.TIMING, isa=ISA.X86, num_cores=args.cores
        )
    elif args.atomic_from_start:
        # Processor that starts in atomic, then goes to timing.
        processor = SimpleSwitchableProcessor(
            starting_core_type=CPUTypes.ATOMIC,
            switch_core_type=CPUTypes.TIMING,
            isa=ISA.X86,
            num_cores=args.cores,
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

        # Here we tell the KVM CPU (the starting CPU) not to use perf.
        for proc in processor.start:
            proc.core.usePerf = False

    # Here we setup the board. The X86Board allows for Full-System X86 simulations.
    board = X86Board(
        clk_freq="3GHz",
        processor=processor,
        memory=memory,
        cache_hierarchy=cache_hierarchy,
    )

    return board, processor
