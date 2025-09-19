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
    IntegrityVerifier,
    L1XBar,
    L2XBar,
    PageSwapper,
    Port,
    SystemXBar,
)
from m5.util.convert import toMemorySize

from ....isas import ISA
from ....utils.override import *
from ...boards.abstract_board import AbstractBoard
from ..abstract_cache_hierarchy import AbstractCacheHierarchy
from ..abstract_two_level_cache_hierarchy import AbstractTwoLevelCacheHierarchy
from .abstract_classic_cache_hierarchy import AbstractClassicCacheHierarchy
from .caches.l1dcache import L1DCache
from .caches.l1icache import L1ICache
from .caches.l2cache import L2Cache
from .caches.mmu_cache import MMUCache


class PrivateL1SharedL2CacheHierarchyIntegrityVerifier(
    AbstractClassicCacheHierarchy, AbstractTwoLevelCacheHierarchy
):
    """
    A cache setup where each core has a private L1 Data and Instruction Cache,
    and a L2 cache is shared with all cores. The shared L2 cache is mostly
    inclusive with respect to the split I/D L1 and MMU caches.

    In addition, an instrumented 'integrity bridge' is added, which manages
    behavior in an integrity structure for memory.
    """

    def _get_default_membus(self) -> SystemXBar:
        """
        A method used to obtain the default memory bus of 64 bit in width for
        the PrivateL1SharedL2 CacheHierarchy.

        :returns: The default memory bus for the PrivateL1SharedL2
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
        l1d_assoc: int = 8,
        l1i_assoc: int = 8,
        l2_assoc: int = 16,
        unified_l1_cache: bool = False,
        membus: Optional[BaseXBar] = None,
        metadata_cache_type: Optional[str] = None,
        metadata_cache_size: Optional[int] = 0,
        metadata_cache_size_tree_nodes: Optional[int] = 0,
        metadata_cache_size_counter_nodes: Optional[int] = 0,
        metadata_cache_size_mac_nodes: Optional[int] = 0,
        metadata_cache_assoc: Optional[int] = 0,
        integrity_allocation_mode: Optional[str] = None,
        integrity_tree_type: Optional[str] = None,
        integrity_tree_arity: Optional[int] = 0,
        use_page_swapper: Optional[bool] = False,
        page_swap_epoch: Optional[int] = 200,
    ) -> None:
        """
        :param l1d_size: The size of the L1 Data Cache (e.g., "32KiB").
        :param  l1i_size: The size of the L1 Instruction Cache (e.g., "32KiB").
        :param l2_size: The size of the L2 Cache (e.g., "256KiB").
        :param l1d_assoc: The associativity of the L1 Data Cache.
        :param l1i_assoc: The associativity of the L1 Instruction Cache.
        :param l2_assoc: The associativity of the L2 Cache.
        :param membus: The memory bus. This parameter is optional parameter and
                       will default to a 64 bit width SystemXBar is not
                       specified.
        :param metadata_cache_size: The size of the metadata cache by the
                                    number of entries it can store. This
                                    parameter is optional.
        """

        AbstractClassicCacheHierarchy.__init__(self=self)
        AbstractTwoLevelCacheHierarchy.__init__(
            self,
            l1i_size=l1i_size,
            l1i_assoc=l1i_assoc,
            l1d_size=l1d_size,
            l1d_assoc=l1d_assoc,
            l2_size=l2_size,
            l2_assoc=l2_assoc,
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

        self._integrity_allocation_mode = integrity_allocation_mode

        if integrity_tree_type == "None":
            integrity_tree_type = None
        self._integrity_tree_type = integrity_tree_type

        if integrity_tree_arity:
            assert integrity_tree_arity >= 0
            self._integrity_tree_arity = integrity_tree_arity

        self._use_page_swapper = use_page_swapper

        self._page_swap_epoch = page_swap_epoch

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
        self.l2bus = L2XBar()
        self.l2cache = L2Cache(size=self._l2_size, assoc=self._l2_assoc)
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
                self.l1icaches[i].mem_side = self.l2bus.cpu_side_ports
                self.l1dcaches[i].mem_side = self.l2bus.cpu_side_ports
            else:
                # Combined I/D cache
                # CPU <--> L1 bus <--> L1 <--> L2 bus
                cpu.connect_icache(self.l1buses[i].cpu_side_ports)
                cpu.connect_dcache(self.l1buses[i].cpu_side_ports)
                self.l1caches[i].cpu_side = self.l1buses[i].mem_side_ports
                self.l1caches[i].mem_side = self.l2bus.cpu_side_ports

            self.iptw_caches[i].mem_side = self.l2bus.cpu_side_ports
            self.dptw_caches[i].mem_side = self.l2bus.cpu_side_ports

            cpu.connect_walker_ports(
                self.iptw_caches[i].cpu_side, self.dptw_caches[i].cpu_side
            )

            if board.get_processor().get_isa() == ISA.X86:
                int_req_port = self.membus.mem_side_ports
                int_resp_port = self.membus.cpu_side_ports
                cpu.connect_interrupt(int_req_port, int_resp_port)
            else:
                cpu.connect_interrupt()

        self.l2bus.mem_side_ports = self.l2cache.cpu_side

        self.verifier = IntegrityVerifier(
            read_req="10ns",
            read_resp="10ns",
            write_req="10ns",
            write_resp="10ns",
            # req_size = 512,
            # resp_size = 512,
            metadata_cache_size=self._metadata_cache_size,
            metadata_cache_assoc=self._metadata_cache_assoc,
        )
        self.verifier.cpu_side_port = self.l2cache.mem_side
        self.membus.cpu_side_ports = self.verifier.mem_side_port

        # Memory <--> NCX <--> membus
        if board.use_ncx():
            if self._use_page_swapper:
                # If using the page swapper, place it between memory bus and NCX.
                self.page_swapper = PageSwapper(
                    swap_epoch=self._page_swap_epoch,
                )
                self.page_swapper.cpu_side_port = self.membus.mem_side_ports
                board.get_ncx().cpu_side_ports = (
                    self.page_swapper.mem_side_port
                )
            else:
                # If not using the page swapper, connect the NCX to the
                # memory bus directly.
                # self.membus.cpu_side_ports = self.verifier.mem_side_port
                self.membus.mem_side_ports = board.get_ncx().cpu_side_ports

            # Connect memory to NCX.
            for _, port in board.get_mem_ports():
                board.get_ncx().mem_side_ports = port

        # Memory <--> membus
        else:
            # The page swapper cannot work without NCX, as it does not have multiple ports implemented.
            assert not self._use_page_swapper

            # Do not use NCX. Connect memory directly to membus.
            for _, port in board.get_mem_ports():
                self.membus.mem_side_ports = port

        dram_memory = None
        cxl_memory = None
        primary_memory = board.get_indexed_memory(0)
        primary_full_range = AddrRange(
            start=board.get_starting_memory_addr(0),
            size=primary_memory.get_size(),
        )
        primary_os_range = AddrRange(
            start=board.get_starting_memory_addr(0),
            size=primary_memory.get_os_size(),
        )
        match board._main_memory_type:
            case "DRAM":
                dram_memory = primary_memory
                dram_full_range = primary_full_range
                dram_os_range = primary_os_range

            case "CXL":
                cxl_memory = primary_memory
                cxl_full_range = primary_full_range
                cxl_os_range = primary_os_range

            case _:
                pass

        secondary_memory = board.get_indexed_memory(1)
        if secondary_memory:
            secondary_full_range = AddrRange(
                start=board.get_starting_memory_addr(1),
                size=secondary_memory.get_size(),
            )
            secondary_os_range = AddrRange(
                start=board.get_starting_memory_addr(1),
                size=secondary_memory.get_os_size(),
            )
            match board._secondary_memory_type:
                case "DRAM":
                    # The case where there are two DRAMs is not yet handled.
                    assert dram_memory is None
                    dram_memory = secondary_memory
                    dram_full_range = secondary_full_range
                    dram_os_range = secondary_os_range

                case "CXL":
                    # The case where there are two CXL memories is not yet handled.
                    assert cxl_memory is None
                    cxl_memory = secondary_memory
                    cxl_full_range = secondary_full_range
                    cxl_os_range = secondary_os_range

                case _:
                    pass

        # Configure verifier and page swapper (if applicable)
        if dram_memory is not None:
            self.verifier.dram_full_range = dram_full_range
            self.verifier.dram_os_range = dram_os_range

            if self._use_page_swapper:
                self.page_swapper.dram_full_range = dram_full_range
                self.page_swapper.dram_os_range = dram_os_range

        if cxl_memory is not None:
            self.verifier.cxl_full_range = cxl_full_range
            self.verifier.cxl_os_range = cxl_os_range

            if self._use_page_swapper:
                self.page_swapper.cxl_full_range = cxl_full_range
                self.page_swapper.cxl_os_range = cxl_os_range

        if self._integrity_allocation_mode:
            self.verifier.integrity_allocation_mode = (
                self._integrity_allocation_mode
            )

        if self._integrity_tree_type:
            self.verifier.integrity_tree_type = self._integrity_tree_type

        if self._integrity_tree_arity:
            self.verifier.integrity_tree_arity = self._integrity_tree_arity

        if self._metadata_cache_type:
            self.verifier.metadata_cache_type = self._metadata_cache_type

        if self._metadata_cache_size_tree_nodes:
            self.verifier.metadata_cache_size_tree_nodes = (
                self._metadata_cache_size_tree_nodes
            )

        if self._metadata_cache_size_counter_nodes:
            self.verifier.metadata_cache_size_counter_nodes = (
                self._metadata_cache_size_counter_nodes
            )

        if self._metadata_cache_size_mac_nodes:
            self.verifier.metadata_cache_size_mac_nodes = (
                self._metadata_cache_size_mac_nodes
            )

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
