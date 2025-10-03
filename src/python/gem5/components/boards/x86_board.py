# Copyright (c) 2021 The Regents of the University of California
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


from typing import (
    List,
    Optional,
    Sequence,
    Tuple,
)

from m5.objects import (
    Addr,
    AddrRange,
    BaseXBar,
    Bridge,
    CommMonitor,
    CowDiskImage,
    CXLBridge,
    CXLMemBar,
    CXLMemory,
    IdeDisk,
    IOXBar,
    NoncoherentXBar,
    Pc,
    Port,
    RawDiskImage,
    SimpleMemDelay,
    X86ACPIMadt,
    X86ACPIMadtIntSourceOverride,
    X86ACPIMadtIOAPIC,
    X86ACPIMadtLAPIC,
    X86E820Entry,
    X86FsLinux,
    X86IntelMPBus,
    X86IntelMPBusHierarchy,
    X86IntelMPIOAPIC,
    X86IntelMPIOIntAssignment,
    X86IntelMPProcessor,
    X86SMBiosBiosInformation,
)
from m5.objects.CXLMemory import CXLMemory
from m5.params import Latency
from m5.util.convert import toMemorySize

from ...components.boards.se_binary_workload import SEBinaryWorkload
from ...isas import ISA
from ...resources.resource import AbstractResource
from ...utils.override import overrides
from ..cachehierarchies.abstract_cache_hierarchy import AbstractCacheHierarchy
from ..memory.abstract_memory_system import AbstractMemorySystem
from ..processors.abstract_processor import AbstractProcessor
from .abstract_board import AbstractBoard
from .abstract_system_board import AbstractSystemBoard
from .kernel_disk_workload import KernelDiskWorkload


class X86Board(AbstractSystemBoard, KernelDiskWorkload, SEBinaryWorkload):
    """
    A board capable of full system simulation for X86.

    **Limitations**
    * Currently, this board's memory is hardcoded to 3GiB.
    * Much of the I/O subsystem is hard coded.
    """

    def __init__(
        self,
        clk_freq: str,
        processor: AbstractProcessor,
        cache_hierarchy: AbstractCacheHierarchy,
        memory: Optional[List[AbstractMemorySystem]] = [],
        cxl_mode: Optional[str] = "Disabled",
        cxl_memory: Optional[AbstractMemorySystem] = None,
        is_asic: Optional[bool] = False,
        main_memory_type: Optional[str] = "DRAM",
        # Use noncoherent-xbar
        use_ncx: Optional[bool] = False,
        cxl_latency: Optional[str] = "35ns",
        cxl_latency_read_req: Optional[str] = None,
        cxl_latency_read_resp: Optional[str] = None,
        cxl_latency_write_req: Optional[str] = None,
        cxl_latency_write_resp: Optional[str] = None,
    ) -> None:
        super().__init__(
            clk_freq=clk_freq,
            processor=processor,
            memory=memory,
            cache_hierarchy=cache_hierarchy,
            cxl_mode=cxl_mode,
            cxl_memory=cxl_memory,
            is_asic=is_asic,
            main_memory_type=main_memory_type,
            use_ncx=use_ncx,
            cxl_latency=cxl_latency,
            cxl_latency_read_req=cxl_latency_read_req,
            cxl_latency_read_resp=cxl_latency_read_resp,
            cxl_latency_write_req=cxl_latency_write_req,
            cxl_latency_write_resp=cxl_latency_write_resp,
        )

        if self.get_processor().get_isa() != ISA.X86:
            raise Exception(
                "The X86Board requires a processor using the X86 "
                f"ISA. Current processor ISA: '{processor.get_isa().name}'."
            )

    @overrides(AbstractBoard)
    def get_starting_memory_addr(self, index: int) -> Addr:
        starts = [
            # Beginning of memory
            Addr(0),
            # 4GB mark (after I/O hole)
            Addr(0x100000000),
        ]

        # Dynamically build the next starting memory address(es) based on
        # used memory
        # i = 1
        last_start = 0x100000000
        for i in range(1, len(self._indexed_memory) - 1):
            starts.append(
                Addr(last_start + self._indexed_memory[i].get_size())
            )
            last_start += self._indexed_memory[i].get_size()

        return starts[index]

    @overrides(AbstractSystemBoard)
    def _setup_board(self) -> None:
        if self.is_fullsystem():
            self.pc = Pc()
            # Add CXL memory if necessary
            if self._cxl_mode == "PCIe":
                self.pc.south_bridge.cxlmemory = CXLMemory(
                    pci_func=0, pci_dev=6, pci_bus=0
                )

            self.workload = X86FsLinux()

            # North Bridge
            self.iobus = IOXBar()

            # Set up all of the I/O.
            self._setup_io_devices()

            self.m5ops_base = 0xFFFF0000

    def _setup_io_devices(self):
        """Sets up the x86 IO devices.

        .. note::

            This is mostly copy-paste from prior X86 FS setups. Some of it
            may not be documented and there may be bugs.
        """

        # Constants similar to x86_traits.hh
        IO_address_space_base = 0x8000000000000000
        pci_config_address_space_base = 0xC000000000000000
        interrupts_address_space_base = 0xA000000000000000
        APIC_range_size = 1 << 12

        # Setup memory system specific settings.
        if self.get_cache_hierarchy().is_ruby():
            if self._cxl_mode == "PCIe":
                self.pc.attachIO(
                    self.get_io_bus(),
                    [
                        self.pc.south_bridge.ide.dma,
                        self.pc.south_bridge.cxlmemory.dma,
                    ],
                    cxl_mode=self._cxl_mode,
                )
            else:
                self.pc.attachIO(
                    self.get_io_bus(),
                    [self.pc.south_bridge.ide.dma],
                    cxl_mode=self._cxl_mode,
                )
        else:
            if self._cxl_mode == "PCIe":
                # Configure CXLBridge
                self.bridge = CXLBridge(
                    bridge_lat="50ns",
                    proto_proc_lat="12ns",
                    req_fifo_depth=128,
                    resp_fifo_depth=128,
                )
            else:
                # Default bridge
                self.bridge = Bridge(delay="50ns")
            self.bridge.mem_side_port = self.get_io_bus().cpu_side_ports
            self.bridge.cpu_side_port = (
                self.get_cache_hierarchy().get_mem_side_port()
            )

            self.bridge.ranges = [
                AddrRange(0xC0000000, 0xFFFF0000),
            ]

            self.bridge.ranges.append(
                AddrRange(
                    IO_address_space_base, interrupts_address_space_base - 1
                ),
            )
            self.bridge.ranges.append(
                AddrRange(pci_config_address_space_base, Addr.max),
            )

            # Configure CXL Device
            if self._cxl_mode == "PCIe":
                assert not self.use_ncx()

                # Set starting address of CXL memory
                if self._main_memory_type == "CXL":
                    cxl_mem_start = self.get_starting_memory_addr(0)
                else:
                    cxl_mem_start = self.get_starting_memory_addr(
                        len(self.get_memory())
                    )

                cxl_dram = self.get_cxl_memory()
                cxl_mem_range = AddrRange(
                    Addr(cxl_mem_start), size=cxl_dram.get_size()
                )
                self.bridge.ranges.append(cxl_mem_range)
                self.pc.south_bridge.cxlmemory.cxl_mem_range = cxl_mem_range
                cxl_dram.set_memory_range([cxl_mem_range])
                cxl_abstract_mems = []
                for mc in cxl_dram.get_memory_controllers():
                    cxl_abstract_mems.append(mc.dram)
                self.memories.extend(cxl_abstract_mems)
                self.cxl_mem_bus = CXLMemBar()
                self.cxl_mem_bus.cpu_side_ports = (
                    self.pc.south_bridge.cxlmemory.mem_req_port
                )
                for _, port in cxl_dram.get_mem_ports():
                    self.cxl_mem_bus.mem_side_ports = port

                self.pc.south_bridge.cxlmemory.BAR0.size = (
                    cxl_dram.get_size_str()
                )
                if self._is_asic:
                    self.pc.south_bridge.cxlmemory.proto_proc_lat = Latency(
                        "15ns"
                    )
                    self.pc.south_bridge.cxlmemory.rsp_size = 48
                    self.pc.south_bridge.cxlmemory.req_size = 48
                else:
                    self.pc.south_bridge.cxlmemory.proto_proc_lat = Latency(
                        "60ns"
                    )
                    self.pc.south_bridge.cxlmemory.rsp_size = 36
                    self.pc.south_bridge.cxlmemory.req_size = 36
            elif self._cxl_mode == "DRAM":
                self.cxl_comm_monitor = CommMonitor()

                # Connect the CXL comm monitor to the bottom of the cache hierarchy or NCX, whichever is lower
                if not self.use_ncx():
                    self.cxl_comm_monitor.cpu_side_port = (
                        self.get_cache_hierarchy().get_mem_side_port()
                    )
                else:
                    self.cxl_comm_monitor.cpu_side_port = (
                        self.get_ncx().mem_side_ports
                    )

                # Add CXL communication latency
                # Any of the more specific parameters will override the generic latency.
                # It is recommended to change all of these values if changing one,
                # so that the values are more predictable.
                delay_time_read_req = (
                    self._cxl_latency_read_req or self._cxl_latency
                )
                delay_time_read_resp = (
                    self._cxl_latency_read_resp or self._cxl_latency
                )
                delay_time_write_req = (
                    self._cxl_latency_write_req or self._cxl_latency
                )
                delay_time_write_resp = (
                    self._cxl_latency_write_resp or self._cxl_latency
                )
                self.cxl_delay = SimpleMemDelay(
                    read_req=delay_time_read_req,
                    read_resp=delay_time_read_resp,
                    write_req=delay_time_write_req,
                    write_resp=delay_time_write_resp,
                )
                self.cxl_delay.cpu_side_port = (
                    self.cxl_comm_monitor.mem_side_port
                )

                # Add CXL XBar to merge multiple MemCtrls into one port on CXL delay
                self.cxl_xbar = NoncoherentXBar(
                    frontend_latency=2,
                    forward_latency=1,
                    response_latency=2,
                    width=16,  # 128 bits
                )
                self.cxl_xbar.cpu_side_ports = self.cxl_delay.mem_side_port

                cxl_dram = self.get_cxl_memory()

                # Attach CXL memory to delay module with CXL XBar to merge them together (one per MemCtrl)
                for i, (_, port) in enumerate(cxl_dram.get_mem_ports()):
                    self.cxl_xbar.mem_side_ports = port

            self.apicbridge = Bridge(delay="50ns")
            self.apicbridge.cpu_side_port = self.get_io_bus().mem_side_ports
            self.apicbridge.mem_side_port = (
                self.get_cache_hierarchy().get_cpu_side_port()
            )
            self.apicbridge.ranges = [
                AddrRange(
                    interrupts_address_space_base,
                    interrupts_address_space_base
                    + self.get_processor().get_num_cores() * APIC_range_size
                    - 1,
                )
            ]
            self.pc.attachIO(self.get_io_bus(), cxl_mode=self._cxl_mode)

        # Add in a Bios information structure.
        self.workload.smbios_table.structures = [X86SMBiosBiosInformation()]

        # Set up the Intel MP table
        base_entries = []
        ext_entries = []
        # Updated the X86 board with MADT entries.
        if self._cxl_mode != "PCIe":
            madt_entries = []
        for i in range(self.get_processor().get_num_cores()):
            bp = X86IntelMPProcessor(
                local_apic_id=i,
                local_apic_version=0x14,
                enable=True,
                bootstrap=(i == 0),
            )
            base_entries.append(bp)
            if self._cxl_mode != "PCIe":
                lapic = X86ACPIMadtLAPIC(
                    acpi_processor_id=i, apic_id=i, flags=1
                )
                madt_entries.append(lapic)

        io_apic = X86IntelMPIOAPIC(
            id=self.get_processor().get_num_cores(),
            version=0x11,
            enable=True,
            address=0xFEC00000,
        )

        self.pc.south_bridge.io_apic.apic_id = io_apic.id
        base_entries.append(io_apic)
        if self._cxl_mode != "PCIe":
            madt_entries.append(
                X86ACPIMadtIOAPIC(
                    id=io_apic.id, address=io_apic.address, int_base=0
                )
            )

        pci_bus = X86IntelMPBus(bus_id=0, bus_type="PCI   ")
        base_entries.append(pci_bus)
        isa_bus = X86IntelMPBus(bus_id=1, bus_type="ISA   ")
        base_entries.append(isa_bus)
        connect_busses = X86IntelMPBusHierarchy(
            bus_id=1, subtractive_decode=True, parent_bus=0
        )
        ext_entries.append(connect_busses)

        pci_dev4_inta = X86IntelMPIOIntAssignment(
            interrupt_type="INT",
            polarity="ConformPolarity",
            trigger="ConformTrigger",
            source_bus_id=0,
            source_bus_irq=0 + (4 << 2),
            dest_io_apic_id=io_apic.id,
            dest_io_apic_intin=16,
        )

        base_entries.append(pci_dev4_inta)
        if self._cxl_mode != "PCIe":
            pci_dev4_inta_madt = X86ACPIMadtIntSourceOverride(
                bus_source=pci_dev4_inta.source_bus_id,
                irq_source=pci_dev4_inta.source_bus_irq,
                sys_int=pci_dev4_inta.dest_io_apic_intin,
                flags=0,
            )
            madt_entries.append(pci_dev4_inta_madt)

        def assignISAInt(irq, apicPin):
            assign_8259_to_apic = X86IntelMPIOIntAssignment(
                interrupt_type="ExtInt",
                polarity="ConformPolarity",
                trigger="ConformTrigger",
                source_bus_id=1,
                source_bus_irq=irq,
                dest_io_apic_id=io_apic.id,
                dest_io_apic_intin=0,
            )
            base_entries.append(assign_8259_to_apic)

            assign_to_apic = X86IntelMPIOIntAssignment(
                interrupt_type="INT",
                polarity="ConformPolarity",
                trigger="ConformTrigger",
                source_bus_id=1,
                source_bus_irq=irq,
                dest_io_apic_id=io_apic.id,
                dest_io_apic_intin=apicPin,
            )
            base_entries.append(assign_to_apic)
            if self._cxl_mode != "PCIe":
                # acpi
                assign_to_apic_acpi = X86ACPIMadtIntSourceOverride(
                    bus_source=1, irq_source=irq, sys_int=apicPin, flags=0
                )
                madt_entries.append(assign_to_apic_acpi)

        assignISAInt(0, 2)
        assignISAInt(1, 1)

        for i in range(3, 15):
            assignISAInt(i, i)

        self.workload.intel_mp_table.base_entries = base_entries
        self.workload.intel_mp_table.ext_entries = ext_entries

        if self._cxl_mode != "PCIe":
            madt = X86ACPIMadt(
                local_apic_address=0, records=madt_entries, oem_id="madt"
            )
            self.workload.acpi_description_table_pointer.rsdt.entries.append(
                madt
            )
            self.workload.acpi_description_table_pointer.xsdt.entries.append(
                madt
            )
            self.workload.acpi_description_table_pointer.oem_id = "gem5"
            self.workload.acpi_description_table_pointer.rsdt.oem_id = "gem5"
            self.workload.acpi_description_table_pointer.xsdt.oem_id = "gem5"

        # Set up the OS-observable memory
        # Primary memory
        if self._main_memory_type == "DRAM":
            primary_memory = self.get_memory()
            primary_mem_full_ranges = [
                AddrRange(
                    start=self.get_starting_memory_addr(i),
                    size=primary_memory[i].get_size(),
                )
                for i in range(len(primary_memory))
            ]
            primary_mem_os_ranges = [
                AddrRange(
                    start=self.get_starting_memory_addr(i),
                    size=primary_memory[i].get_os_size(),
                )
                for i in range(len(primary_memory))
            ]
            for i in range(len(primary_memory)):
                print(
                    f"{self._main_memory_type} Memory Range [{i}] (Full): ({primary_mem_full_ranges[i]})"
                )
                print(
                    f"{self._main_memory_type} Memory Range [{i}] (OS-observable): ({primary_mem_os_ranges[i]})"
                )
        else:
            raise Exception(
                f"Unsupported main memory type '{self._main_memory_type}"
            )

        # Secondary memory
        # NOTE: Currently assumes there is DRAM added as primary memory.
        secondary_memory = self.get_indexed_memory(len(self.get_memory()))
        if secondary_memory is not None:
            secondary_mem_full_range = AddrRange(
                start=self.get_starting_memory_addr(len(self.get_memory())),
                size=secondary_memory.get_size(),
            )
            secondary_mem_os_range = AddrRange(
                start=self.get_starting_memory_addr(len(self.get_memory())),
                size=secondary_memory.get_os_size(),
            )
            print(
                f"{self._secondary_memory_type} Memory Range (Full): ({secondary_mem_full_range})"
            )
            print(
                f"{self._secondary_memory_type} Memory Range (OS-observable): ({secondary_mem_os_range})"
            )

        entries = [
            # Mark the first megabyte of memory as reserved
            X86E820Entry(addr=0, size="639KiB", range_type=1),
            X86E820Entry(addr=0x9FC00, size="385KiB", range_type=2),
        ]

        # Add primary memory range
        if primary_memory[0].get_size() > toMemorySize("3GiB"):
            raise Exception(
                "Main memory is provided as more than 3GB, which is "
                "currently unsupported."
            )
        entries.append(
            X86E820Entry(
                addr=0x100000,
                size=f"{primary_memory[0].get_os_size() - 0x100000:d}B",
                range_type=1,
            ),
        )

        # Reserve the last 16KiB of the 32-bit address space for m5ops
        entries.append(
            X86E820Entry(addr=0xFFFF0000, size="64KiB", range_type=2)
        )

        # Add remaining primary memory, if applicable.
        for i in range(1, len(self.get_memory())):
            entries.append(
                X86E820Entry(
                    addr=self.get_starting_memory_addr(i),
                    size=f"{primary_memory[i].get_os_size()}B",
                    range_type=1,
                )
            )

        # Add secondary memory if applicable.
        if secondary_memory is not None:
            entries.append(
                X86E820Entry(
                    addr=self.get_starting_memory_addr(len(self.get_memory())),
                    size=f"{secondary_memory.get_os_size()}B",
                    range_type=1,
                )
            )

        self.workload.e820_table.entries = entries

    @overrides(AbstractSystemBoard)
    def has_io_bus(self) -> bool:
        return self.is_fullsystem()

    @overrides(AbstractSystemBoard)
    def get_io_bus(self) -> IOXBar:
        if self.has_io_bus():
            return self.iobus
        else:
            raise Exception(
                "Cannot execute `get_io_bus()`: Board does not have an I/O "
                "bus to return. Use `has_io_bus()` to check this."
            )

    @overrides(AbstractSystemBoard)
    def has_dma_ports(self) -> bool:
        return self.is_fullsystem()

    @overrides(AbstractSystemBoard)
    def get_dma_ports(self) -> Sequence[Port]:
        if self.has_dma_ports():
            if self._cxl_mode == "PCIe":
                return [
                    self.pc.south_bridge.ide.dma,
                    self.iobus.mem_side_ports,
                    self.pc.south_bridge.cxlmemory.dma,
                ]
            else:
                return [
                    self.pc.south_bridge.ide.dma,
                    self.iobus.mem_side_ports,
                ]
        else:
            raise Exception(
                "Cannot execute `get_dma_ports()`: Board does not have DMA "
                "ports to return. Use `has_dma_ports()` to check this."
            )

    @overrides(AbstractSystemBoard)
    def has_coherent_io(self) -> bool:
        return self.is_fullsystem()

    @overrides(AbstractSystemBoard)
    def get_mem_side_coherent_io_port(self) -> Port:
        if self.has_coherent_io():
            return self.iobus.mem_side_ports
        else:
            raise Exception(
                "Cannot execute `get_mem_side_coherent_io_port()`: Board does "
                "not have I/O ports to return. Use `has_coherent_io()` to "
                "check this."
            )

    @overrides(AbstractSystemBoard)
    def _setup_memory_ranges(self):
        # Due to supporting multiple DRAM controllers, this assertion
        # is added at this time.
        assert self._main_memory_type == "DRAM"

        # Associate memory ranges with memory.
        primary_memory = self.get_memory()
        primary_ranges = [
            AddrRange(
                start=self.get_starting_memory_addr(i),
                size=primary_memory[i].get_size(),
            )
            for i in range(len(primary_memory))
        ]
        for i, memory in enumerate(primary_memory):
            memory.set_memory_range([primary_ranges[i]])
        if primary_memory[0].get_size() > toMemorySize("3GiB"):
            raise Exception(
                "X86Board currently only supports memory sizes up "
                "to 3GiB because of the I/O hole."
            )

        secondary_memory = self.get_indexed_memory(len(self.get_memory()))
        if secondary_memory:
            secondary_range = AddrRange(
                start=self.get_starting_memory_addr(len(self.get_memory())),
                size=secondary_memory.get_size(),
            )
            secondary_memory.set_memory_range([secondary_range])

        # Add abstract memory to parent System class. (Only applies to DRAM-like memory.)
        cpu_abstract_mems = []
        if self._main_memory_type == "DRAM" or (
            self._main_memory_type == "CXL" and self._cxl_mode == "DRAM"
        ):
            # DRAM is primary memory. Nothing crazy here.
            for memory in primary_memory:
                for mc in memory.get_memory_controllers():
                    try:
                        cpu_abstract_mems.append(mc.dram)
                    except AttributeError:
                        # Fallback for simple memory
                        cpu_abstract_mems.append(mc)
        if secondary_memory and (
            self._secondary_memory_type == "DRAM"
            or (
                self._secondary_memory_type == "CXL"
                and self._cxl_mode == "DRAM"
            )
        ):
            for mc in secondary_memory.get_memory_controllers():
                try:
                    cpu_abstract_mems.append(mc.dram)
                except AttributeError:
                    # Fallback for simple memory
                    cpu_abstract_mems.append(mc)

        self.memories = cpu_abstract_mems

        # Add the address range for the IO. (Only applies to DRAM-like memory.)
        self.mem_ranges = []

        if self._main_memory_type == "DRAM" or (
            self._main_memory_type == "CXL" and self._cxl_mode == "DRAM"
        ):
            for r in primary_ranges:
                self.mem_ranges.append(r)

        self.mem_ranges.append(
            AddrRange(0xC0000000, size=0x100000),  # For I/0
        )

        if secondary_memory and (
            self._secondary_memory_type == "DRAM"
            or (
                self._secondary_memory_type == "CXL"
                and self._cxl_mode == "DRAM"
            )
        ):
            self.mem_ranges.append(secondary_range)

    @overrides(KernelDiskWorkload)
    def get_disk_device(self):
        if self._cxl_mode == "PCIe":
            return "/dev/hda1"
        else:
            return "/dev/hda"

    @overrides(KernelDiskWorkload)
    def _add_disk_to_board(self, disk_image: AbstractResource):
        ide_disk = IdeDisk()
        ide_disk.driveID = "device0"
        ide_disk.image = CowDiskImage(
            child=RawDiskImage(read_only=True), read_only=False
        )
        ide_disk.image.child.image_file = disk_image.get_local_path()

        # Attach the SimObject to the system.
        self.pc.south_bridge.ide.disks = [ide_disk]

    @overrides(KernelDiskWorkload)
    def get_default_kernel_args(self) -> List[str]:
        return [
            "earlyprintk=ttyS0",
            "console=ttyS0",
            "lpj=7999923",
            "root={root_value}",
            "disk_device={disk_device}",
        ]
