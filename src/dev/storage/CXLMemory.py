from m5.objects.PciDevice import *
from m5.params import *


class CXLMemory(PciDevice):
    type = "CXLMemory"
    cxx_header = "dev/storage/cxl_memory.hh"
    cxx_class = "gem5::CXLMemory"

    cxl_rsp_port = ResponsePort(
        "This port sends responses to and receives requests from the Host"
    )
    mem_req_port = RequestPort(
        "This port sends requests to and receives responses from the back-end memory media"
    )

    rsp_size = Param.Unsigned(48, "The number of responses to buffer")
    req_size = Param.Unsigned(48, "The number of requests to buffer")

    proto_proc_lat = Param.Latency(
        "15ns",
        "Latency of the CXL controller processing CXL.mem sub-protocol packets",
    )
    cxl_mem_range = Param.AddrRange(
        "2GiB",
        "CXL expander memory range that can be identified as system memory",
    )

    VendorID = 0x8086  # Intel
    DeviceID = 0x7890  # Custom ID
    Command = 0x0  # https://wiki.osdev.org/PCI#Command_Register
    Status = 0x280  # https://wiki.osdev.org/PCI#Status_Register
    Revision = 0x0
    ClassCode = 0x05  # Memory controller
    SubClassCode = 0x00  # RAM
    ProgIF = 0x00  # RAM controller
    InterruptLine = 0x1F
    InterruptPin = 0x01  # Pin A

    # Primary
    BAR0 = PciMemBar(size="2GiB")
    BAR1 = PciMemUpperBar()
