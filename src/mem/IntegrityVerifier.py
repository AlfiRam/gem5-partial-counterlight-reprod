# Copyright (c) 2018 ARM Limited
# All rights reserved.
#
# The license below extends only to copyright in the software and shall
# not be construed as granting a license to any other intellectual
# property including but not limited to intellectual property relating
# to a hardware implementation of the functionality of the software
# licensed hereunder.  You may use the software subject to the license
# terms below provided that you ensure that this notice is replicated
# unmodified and in its entirety in all distributions of the software,
# modified or unmodified, in source code or in binary form.
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

from m5.objects.ClockedObject import ClockedObject
from m5.params import *
from m5.proxy import *  # Used for Parent.any


class MetadataCacheType(Enum):
    vals = ["MetadataCache", "PartitionedMetadataCache"]


class IntegrityAllocationMode(Enum):
    vals = ["DramOnly", "CxlOnly", "BasicMix"]


class IntegrityTreeType(Enum):
    vals = ["TimingTree", "TimingBmt"]


class AbstractIntegrityVerifier(ClockedObject):
    type = "AbstractIntegrityVerifier"
    cxx_header = "mem/integrity_verifier.hh"
    cxx_class = "gem5::AbstractIntegrityVerifier"
    abstract = True

    mem_side_port = RequestPort(
        "This port sends requests and receives responses"
    )
    cpu_side_port = ResponsePort(
        "This port receives requests and sends responses"
    )

    system = Param.System(Parent.any, "System that the object belongs to.")

    integrity_hashing_latency = Param.Cycles(
        40, "Time in cycles to encrypt or decrypt using an encryption engine."
    )

    metadata_cache_type = Param.MetadataCacheType(
        "MetadataCache", "Class of metadata cache."
    )
    metadata_cache_size = Param.Int(
        6144, "Metadata cache size (Non-partitioned only)"
    )
    metadata_cache_size_tree_nodes = Param.Int(
        2048,
        "Number of tree nodes to store in metadata cache (Partitioned only)",
    )
    metadata_cache_size_counter_nodes = Param.Int(
        2048,
        "Number of counter nodes to store in metadata cache (Partitioned only)",
    )
    metadata_cache_size_mac_nodes = Param.Int(
        2048,
        "Number of MAC nodes to store in metadata cache (Partitioned only)",
    )
    metadata_cache_assoc = Param.Int(8, "Metadata cache associativity")

    # All ranges are assumed to be disjoint and in sorted order.
    dram_full_ranges = VectorParam.AddrRange(
        [], "Full available range(s) of DRAM"
    )
    dram_os_ranges = VectorParam.AddrRange([], "OS-visible range(s) of DRAM")
    cxl_full_ranges = VectorParam.AddrRange(
        [], "Full available range(s) of CXL"
    )
    cxl_os_ranges = VectorParam.AddrRange([], "OS-visible range(s) of DRAM")

    integrity_allocation_mode = Param.IntegrityAllocationMode(
        "DramOnly",
        "The allocation strategy for integrity metadata across DRAM and CXL "
        "memory (if applicable).",
    )

    integrity_tree_type = Param.IntegrityTreeType(
        "TimingTree", "Type of integrity tree class used."
    )

    integrity_tree_arity = Param.Int(4, "Arity of integrity tree.")


class IntegrityVerifier(AbstractIntegrityVerifier):
    type = "IntegrityVerifier"
    cxx_header = "mem/integrity_verifier.hh"
    cxx_class = "gem5::IntegrityVerifier"

    read_req = Param.Latency("0t", "Read request delay")
    read_resp = Param.Latency("0t", "Read response delay")

    write_req = Param.Latency("0t", "Write request delay")
    write_resp = Param.Latency("0t", "Write response delay")
