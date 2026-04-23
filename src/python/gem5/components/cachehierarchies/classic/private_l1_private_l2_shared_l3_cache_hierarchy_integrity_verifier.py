# Copyright (c) 2022 The Regents of the Yonsei University
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


from typing import Optional

from m5.objects import (
    AddrRange,
    BadAddr,
    BaseXBar,
    Bridge,
    Cache,
    DataLocationPartitionManager,
    DynamicCapacityPartitioningPolicy,
    IntegrityPartitionManager,
    IntegrityVerifier,
    L1XBar,
    L2XBar,
    L3XBar,
    Port,
    SystemXBar,
    WayPartitioningPolicy,
    WayPolicyAllocation,
)
from m5.util.convert import toMemorySize

from ....isas import ISA
from ....utils.override import *
from ...boards.abstract_board import AbstractBoard
from ..abstract_cache_hierarchy import AbstractCacheHierarchy
from ..abstract_three_level_cache_hierarchy import (
    AbstractThreeLevelCacheHierarchy,
)
from .abstract_classic_cache_hierarchy import AbstractClassicCacheHierarchy
from .caches.l1dcache import L1DCache
from .caches.l1icache import L1ICache
from .caches.l2cache import L2Cache
from .caches.l3cache import L3Cache
from .caches.metadata import ClassicMetadataCache
from .caches.mmu_cache import MMUCache


class PrivateL1PrivateL2SharedL3CacheHierarchyIntegrityVerifier(
    AbstractClassicCacheHierarchy, AbstractThreeLevelCacheHierarchy
):
    """
    A cache setup where each core has a private L1 Data and Instruction Cache,
    private L2 Cache and a L3 cache is shared with all cores. The shared L3 cache is mostly
    inclusive with respect to the L2 and MMU caches.

    In addition, an instrumented 'integrity bridge' is added, which manages
    behavior in an integrity structure for memory.
    """

    def _get_default_membus(self) -> SystemXBar:
        """
        A method used to obtain the default memory bus of 64 bytes in width for
        the PrivateL1PrivateL2SharedL3 CacheHierarchy.

        :returns: The default memory bus for the PrivateL1PrivateL2SharedL3
                  CacheHierarchy.

        :rtype: SystemXBar
        """
        membus = SystemXBar(width=64)
        membus.badaddr_responder = BadAddr()
        membus.default = membus.badaddr_responder.pio
        return membus

    def _get_default_metadata_cache_size(self) -> int:
        return 2048

    def __init__(
        self,
        l1d_size: str,
        l1i_size: str,
        l2_size: str,
        l3_size: str,
        l1d_assoc: int = 8,
        l1i_assoc: int = 8,
        l2_assoc: int = 16,
        l3_assoc: int = 16,
        unified_l1_cache: bool = False,
        membus: Optional[BaseXBar] = None,
        metadata_cache_type: Optional[str] = None,
        metadata_cache_size: Optional[int] = 0,
        metadata_cache_size_tree_nodes: Optional[int] = 0,
        metadata_cache_size_counter_nodes: Optional[int] = 0,
        metadata_cache_size_mac_nodes: Optional[int] = 0,
        metadata_cache_assoc: Optional[int] = 0,
        unified_upstream_cache: Optional[bool] = False,
        enable_partition_manager: Optional[bool] = False,
        integrity_tree_type: Optional[str] = None,
        integrity_tree_arity: Optional[int] = 0,
    ) -> None:
        # TODO Update documentation
        """
        :param l1d_size: The size of the L1 Data Cache (e.g., "32KiB").
        :param  l1i_size: The size of the L1 Instruction Cache (e.g., "32KiB").
        :param l2_size: The size of the L2 Cache (e.g., "256KiB").
        :param l3_size: The size of the L3 Cache (e.g., "1024KiB").
        :param l1d_assoc: The associativity of the L1 Data Cache.
        :param l1i_assoc: The associativity of the L1 Instruction Cache.
        :param l2_assoc: The associativity of the L2 Cache.
        :param l3_assoc: The associativity of the L3 Cache.
        :param membus: The memory bus. This parameter is optional parameter and
                       will default to a 64 bit width SystemXBar is not
                       specified.
        :param metadata_cache_size: The size of the metadata cache by the
                                    number of entries it can store. This
                                    parameter is optional.
        """

        AbstractClassicCacheHierarchy.__init__(self=self)
        AbstractThreeLevelCacheHierarchy.__init__(
            self,
            l1i_size=l1i_size,
            l1i_assoc=l1i_assoc,
            l1d_size=l1d_size,
            l1d_assoc=l1d_assoc,
            l2_size=l2_size,
            l2_assoc=l2_assoc,
            l3_size=l3_size,
            l3_assoc=l3_assoc,
        )

        self._unified_l1_cache = unified_l1_cache

        self.membus = membus if membus else self._get_default_membus()

        self._metadata_cache_type = metadata_cache_type
        if metadata_cache_size:
            assert metadata_cache_size >= 1
            self._metadata_cache_size = metadata_cache_size
        else:
            self._metadata_cache_size = self._get_default_metadata_cache_size()

        if metadata_cache_size_tree_nodes:
            assert metadata_cache_size_tree_nodes >= 1
            self._metadata_cache_size_tree_nodes = (
                metadata_cache_size_tree_nodes
            )

        if metadata_cache_size_counter_nodes:
            assert metadata_cache_size_counter_nodes >= 1
            self._metadata_cache_size_counter_nodes = (
                metadata_cache_size_counter_nodes
            )

        if metadata_cache_size_mac_nodes:
            assert metadata_cache_size_mac_nodes >= 1
            self._metadata_cache_size_mac_nodes = metadata_cache_size_mac_nodes

        self._metadata_cache_assoc = metadata_cache_assoc

        self._unified_upstream_cache = unified_upstream_cache

        self._enable_partition_manager = enable_partition_manager

        if integrity_tree_type == "None":
            integrity_tree_type = None
        self._integrity_tree_type = integrity_tree_type

        if integrity_tree_arity:
            assert integrity_tree_arity >= 0
            self._integrity_tree_arity = integrity_tree_arity

    @overrides(AbstractClassicCacheHierarchy)
    def get_mem_side_port(self) -> Port:
        return self.membus.mem_side_ports

    @overrides(AbstractClassicCacheHierarchy)
    def get_cpu_side_port(self) -> Port:
        return self.membus.cpu_side_ports

    @overrides(AbstractCacheHierarchy)
    def incorporate_cache(self, board: AbstractBoard) -> None:
        # Set up the system port for functional access from the simulator.
        board.connect_system_port(self.membus.cpu_side_ports)

        if not self._unified_l1_cache:
            # Separate I/D cache
            self.l1icaches = [
                L1ICache(
                    size=self._l1i_size,
                    assoc=self._l1i_assoc,
                    writeback_clean=False,
                )
                for i in range(board.get_processor().get_num_cores())
            ]
            self.l1dcaches = [
                L1DCache(size=self._l1d_size, assoc=self._l1d_assoc)
                for i in range(board.get_processor().get_num_cores())
            ]
        else:
            # Combined I/D cache
            # Use XBar to connect CPU Icache and Dcache port to unified cache
            assert self._l1i_assoc == self._l1d_assoc
            self.l1buses = [
                L1XBar() for i in range(board.get_processor().get_num_cores())
            ]
            self.l1caches = [
                L1DCache(
                    size=f"{toMemorySize(self._l1i_size) + toMemorySize(self._l1d_size)}B",
                    assoc=self._l1i_assoc,
                    writeback_clean=False,
                )
                for i in range(board.get_processor().get_num_cores())
            ]
        self.l2buses = [
            L2XBar() for i in range(board.get_processor().get_num_cores())
        ]
        self.l2caches = [
            L2Cache(size=self._l2_size)
            for i in range(board.get_processor().get_num_cores())
        ]
        self.l3bus = L3XBar()
        self.l3cache = L3Cache(size=self._l3_size, assoc=self._l3_assoc)
        # ITLB Page walk caches
        self.iptw_caches = [
            MMUCache(size="8KiB", writeback_clean=False)
            for _ in range(board.get_processor().get_num_cores())
        ]
        # DTLB Page walk caches
        self.dptw_caches = [
            MMUCache(size="8KiB", writeback_clean=False)
            for _ in range(board.get_processor().get_num_cores())
        ]

        if board.has_coherent_io():
            self._setup_io_cache(board)

        for i, cpu in enumerate(board.get_processor().get_cores()):
            if not self._unified_l1_cache:
                # Separate I/D cache
                # CPU <--> L1D, L1I <--> L2 bus
                cpu.connect_icache(self.l1icaches[i].cpu_side)
                cpu.connect_dcache(self.l1dcaches[i].cpu_side)
                self.l1icaches[i].mem_side = self.l2buses[i].cpu_side_ports
                self.l1dcaches[i].mem_side = self.l2buses[i].cpu_side_ports
            else:
                # Combined I/D cache
                # CPU <--> L1 bus <--> L1 <--> L2 bus
                cpu.connect_icache(self.l1buses[i].cpu_side_ports)
                cpu.connect_dcache(self.l1buses[i].cpu_side_ports)
                self.l1caches[i].cpu_side = self.l1buses[i].mem_side_ports
                self.l1caches[i].mem_side = self.l2buses[i].cpu_side_ports

            self.iptw_caches[i].mem_side = self.l2buses[i].cpu_side_ports
            self.dptw_caches[i].mem_side = self.l2buses[i].cpu_side_ports

            self.l2buses[i].mem_side_ports = self.l2caches[i].cpu_side
            self.l3bus.cpu_side_ports = self.l2caches[i].mem_side

            cpu.connect_walker_ports(
                self.iptw_caches[i].cpu_side, self.dptw_caches[i].cpu_side
            )

            if board.get_processor().get_isa() == ISA.X86:
                int_req_port = self.membus.mem_side_ports
                int_resp_port = self.membus.cpu_side_ports
                cpu.connect_interrupt(int_req_port, int_resp_port)
            else:
                cpu.connect_interrupt()

        self.l3bus.mem_side_ports = self.l3cache.cpu_side
        # self.membus.cpu_side_ports = self.l3cache.mem_side

        self.verifier = IntegrityVerifier(
            read_req="10ns",
            read_resp="10ns",
            write_req="10ns",
            write_resp="10ns",
        )
        self.verifier.cpu_side_port = self.l3cache.mem_side
        self.membus.cpu_side_ports = self.verifier.mem_side_port

        partition_manager = None

        if self._unified_upstream_cache:
            # Metadata cache is part of LLC

            if self._enable_partition_manager:
                partition_manager = DataLocationPartitionManager(
                    partitioning_policies=[
                        DynamicCapacityPartitioningPolicy(
                            partition_ids=[0, 1, 2, 3],
                            capacities=[0.2, 0.2, 0.2, 0.2],
                            update_rate=1000000000,  # 1ms / 0.001s
                        ),
                    ]
                )
                self.l3cache.partitioning_manager = partition_manager

            # Send requests to the LLC with the request port, and
            # responses will be sent through the standard data
            # response port.
            self.l3bus.cpu_side_ports = self.verifier.metadata_req_port
            self.verifier.unified_upstream_cache = True
        else:
            # Use separate metadata cache
            # TODO Options are kind of broken for now

            # Create cache
            if self._metadata_cache_type == "MetadataCache":
                self.metadata_cache = ClassicMetadataCache(
                    size=f"{self._metadata_cache_size * 64}B",
                    assoc=self._metadata_cache_assoc,
                    writeback_clean=False,
                )
            elif self._metadata_cache_type == "PartitionedMetadataCache":
                self.metadata_cache = ClassicMetadataCache(
                    size=f"{self._metadata_cache_size * 64}B",
                    assoc=self._metadata_cache_assoc * 3,
                    writeback_clean=False,
                )
                # Each node type has the normal associativity.
                # We create 3 times the associativity, then split it 3 ways.
                partition_manager = IntegrityPartitionManager(
                    partitioning_policies=[
                        WayPartitioningPolicy(
                            allocations=[
                                # Tree nodes
                                WayPolicyAllocation(
                                    partition_id=0,
                                    ways=[
                                        way
                                        for way in range(
                                            0, self._metadata_cache_assoc
                                        )
                                    ],
                                ),
                                # Counters
                                WayPolicyAllocation(
                                    partition_id=1,
                                    ways=[
                                        way
                                        for way in range(
                                            self._metadata_cache_assoc,
                                            self._metadata_cache_assoc * 2,
                                        )
                                    ],
                                ),
                                # MACs
                                WayPolicyAllocation(
                                    partition_id=2,
                                    ways=[
                                        way
                                        for way in range(
                                            self._metadata_cache_assoc * 2,
                                            self._metadata_cache_assoc * 3,
                                        )
                                    ],
                                ),
                            ]
                        ),
                    ]
                )
                self.metadata_cache.partitioning_manager = partition_manager

            # Attach metadata cache to ports
            self.metadata_cache.cpu_side = self.verifier.metadata_req_port
            self.verifier.metadata_resp_port = self.metadata_cache.mem_side

        # Memory <--> membus
        for _, port in board.get_mem_ports():
            self.membus.mem_side_ports = port

        # Retrieve/compute memory ranges.
        primary_memory = board.get_memory()
        dram_full_ranges = [
            AddrRange(
                start=board.get_starting_memory_addr(i),
                size=primary_memory[i].get_size(),
            )
            for i in range(len(primary_memory))
        ]
        dram_os_ranges = [
            AddrRange(
                start=board.get_starting_memory_addr(i),
                size=primary_memory[i].get_os_size(),
            )
            for i in range(len(primary_memory))
            if primary_memory[i].get_os_size() > 0
        ]

        # Configure verifier
        self.verifier.dram_full_ranges = dram_full_ranges
        self.verifier.dram_os_ranges = dram_os_ranges

        # Advertise address ranges if applicable to partition manager
        if partition_manager is not None:
            try:
                partition_manager.dram_full_ranges = dram_full_ranges
                partition_manager.dram_os_ranges = dram_os_ranges
            except Exception:
                pass

        if self._integrity_tree_type:
            self.verifier.integrity_tree_type = self._integrity_tree_type

        if self._integrity_tree_arity:
            self.verifier.integrity_tree_arity = self._integrity_tree_arity

    def _setup_io_cache(self, board: AbstractBoard) -> None:
        """Create a cache for coherent I/O connections"""
        self.iocache = Cache(
            assoc=8,
            tag_latency=50,
            data_latency=50,
            response_latency=50,
            mshrs=20,
            size="1KiB",
            tgts_per_mshr=12,
            addr_ranges=board.mem_ranges,
        )
        self.iocache.mem_side = self.membus.cpu_side_ports
        self.iocache.cpu_side = board.get_mem_side_coherent_io_port()
