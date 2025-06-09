# Generate a common board configuration across workloads. This also provides
# some additional relevant arguments.

from m5.objects import (
    BadAddr,
    SystemXBar,
)

from gem5.components.boards.x86_board import X86Board
from gem5.components.cachehierarchies.classic.private_l1_shared_l2_cache_hierarchy import (
    PrivateL1SharedL2CacheHierarchy,
)
from gem5.components.cachehierarchies.classic.private_l1_shared_l2_cache_hierarchy_integrity_verifier import (
    PrivateL1SharedL2CacheHierarchyIntegrityVerifier,
)
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
        "--use-integrity-verifier",
        action="store_true",
        help="Add an 'integrity verifier' component to add integrity management behavior.",
    )

    parser.add_argument(
        "--timing-from-start",
        action="store_true",
        help="Instead of switching from KVM cores to timing cores when reaching the POI, use timing cores starting at boot.",
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

    # Main memory
    memory = DIMM_DDR5_4400(size="3GiB", os_size="1800MiB")

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
            os_size="1800MiB",
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

    if not args.timing_from_start:
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
    else:
        # Example of a processor that starts in timing mode, rather than switching to timing after boot.
        processor = SimpleProcessor(
            cpu_type=CPUTypes.TIMING, isa=ISA.X86, num_cores=args.cores
        )

    # Here we setup the board. The X86Board allows for Full-System X86 simulations.
    board = X86Board(
        clk_freq="3GHz",
        processor=processor,
        memory=memory,
        cache_hierarchy=cache_hierarchy,
    )

    return board, processor
