"""
Test tree size calculations.
"""

from create_board import *

from m5.util.convert import toMemorySize

from gem5.components.memory.mtree.TimingTree import TimingTree

dram_os_size, cxl_os_size = TimingTree.determine_max_protected_size(
    min_local_size=toMemorySize("512MiB"),
    total_local_size=toMemorySize("3GiB"),
    total_remote_size=toMemorySize("8GiB"),
    arity=4,
)

print(f"DRAM OS Size: {dram_os_size}")
print(f"CXL OS Size: {cxl_os_size}")
