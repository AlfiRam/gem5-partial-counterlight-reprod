from m5.objects.ClockedObject import ClockedObject
from m5.params import *
from m5.proxy import *  # Used for Parent.any


class AbstractPageSwapper(ClockedObject):
    type = "AbstractPageSwapper"
    cxx_header = "mem/page_swapper.hh"
    cxx_class = "gem5::AbstractPageSwapper"
    abstract = True

    mem_side_port = RequestPort(
        "This port sends requests and receives responses"
    )
    cpu_side_port = ResponsePort(
        "This port receives requests and sends responses"
    )

    system = Param.System(Parent.any, "System that the object belongs to.")

    page_bytes = Param.MemorySize("4KiB", "Size of pages")

    swap_epoch = Param.Int(
        200, "Number of requests between page swap attempts."
    )

    dram_full_ranges = VectorParam.AddrRange(
        [], "Full available range(s) of DRAM"
    )
    dram_os_ranges = VectorParam.AddrRange([], "OS-visible range(s) of DRAM")
    cxl_full_ranges = VectorParam.AddrRange(
        [], "Full available range(s) of CXL"
    )
    cxl_os_ranges = VectorParam.AddrRange([], "OS-visible range(s) of DRAM")


class PageSwapper(AbstractPageSwapper):
    type = "PageSwapper"
    cxx_header = "mem/page_swapper.hh"
    cxx_class = "gem5::PageSwapper"

    read_req = Param.Latency("0t", "Read request delay")
    read_resp = Param.Latency("0t", "Read response delay")

    write_req = Param.Latency("0t", "Write request delay")
    write_resp = Param.Latency("0t", "Write response delay")
