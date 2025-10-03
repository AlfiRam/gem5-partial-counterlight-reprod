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

from abc import ABCMeta
from typing import (
    List,
    Optional,
)

from m5.objects import (
    SimObject,
    System,
)

from ...utils.override import overrides
from .abstract_board import AbstractBoard


class AbstractSystemBoard(System, AbstractBoard):
    """
    An abstract board for cases where boards should inherit from System.
    """

    __metaclass__ = ABCMeta

    def __init__(
        self,
        clk_freq: str,
        processor: "AbstractProcessor",
        cache_hierarchy: "AbstractCacheHierarchy",
        memory: Optional[List["AbstractMemorySystem"]] = [],
        cxl_mode: Optional[str] = "Disabled",
        cxl_memory: Optional["AbstractMemorySystem"] = None,
        is_asic: Optional[bool] = False,
        main_memory_type: Optional[str] = "DRAM",
        use_ncx: Optional[bool] = False,
        cxl_latency: Optional[str] = "35ns",
        cxl_latency_read_req: Optional[str] = None,
        cxl_latency_read_resp: Optional[str] = None,
        cxl_latency_write_req: Optional[str] = None,
        cxl_latency_write_resp: Optional[str] = None,
    ):
        System.__init__(self)
        AbstractBoard.__init__(
            self,
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

    @overrides(SimObject)
    def createCCObject(self):
        """We override this function as it is called in ``m5.instantiate``. This
        means we can insert a check to ensure the ``_connect_things`` function
        has been run.
        """
        super()._connect_things_check()
        super().createCCObject()
