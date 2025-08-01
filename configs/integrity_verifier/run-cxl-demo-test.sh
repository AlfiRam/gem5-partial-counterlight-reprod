#!/bin/bash
{

gem5_binary="./build/X86/gem5.opt"
# gem5_binary="./build/X86/gem5.debug"
config_file="configs/integrity_verifier/basic-demo.py"
# gem5_params="--listener-mode=on"
# gem5_params="--listener-mode=on --debug-flags=AbstractIntegrityVerifier,SimpleMetadataCache,TimingTree,MemCtrl,DRAM"
# gem5_params="--listener-mode=on --debug-flags=AbstractIntegrityVerifierTest"
# gem5_params="--listener-mode=on --debug-flags=AbstractIntegrityVerifierReqs,TimingTree,XBar,BaseXBar"
# gem5_params="--listener-mode=on --debug-flags=AbstractIntegrityVerifierReqs,TimingTree,CXLMemory,Exec,-ExecMicro"
gem5_params="--listener-mode=on --debug-flags=IntegrityNodeLocationMap,IdeDisk"

# redirect="--redirect-stdout --stdout-file stdout.txt --redirect-stderr --stderr-file stderr.txt"
redirect=""

# benchmark_params="--use-integrity-verifier --metadata-cache-size=30000 --enable-cxl"
# benchmark_params="--use-integrity-verifier --metadata-cache-size=2048 --enable-cxl --dram-size=3GiB --cxl-size=4GiB --integrity-allocation-mode=CxlOnly"
# benchmark_params="--use-integrity-verifier --metadata-cache-size=2048 --enable-cxl --dram-size=0 --cxl-size=2GiB --integrity-allocation-mode=CxlOnly --cxl-as-main --timing-from-start"

# outdir="m5out-cxlintegrity-demo"
# outdir="m5out-integrityalloc-cxlonly"

if [ "$2" == "gdb" ]; then
  gdb="gdb --args"
else
  gdb=""
fi


if [ "$1" == "app-dram-integrity-dram" ]; then
  # App data in DRAM, Integrity data in DRAM
  benchmark_params="--use-integrity-verifier --metadata-cache-size=2048 --metadata-cache-assoc=8 --dram-size=3GiB --cxl-size=0 --integrity-allocation-mode=DramOnly"
  outdir="m5out-integrityalloc-appdram-integritydram"

elif [ "$1" == "app-dram-integrity-cxl" ]; then
  # App data in DRAM, Integrity data in CXL
  benchmark_params="--use-integrity-verifier --metadata-cache-size=2048 --metadata-cache-assoc=8 --enable-cxl --dram-size=3GiB --cxl-size=2GiB --integrity-allocation-mode=CxlOnly --no-cxl-for-apps"
  outdir="m5out-integrityalloc-appdram-integritycxl"

elif [ "$1" == "app-cxl-integrity-dram" ]; then
  # App data in CXL, Integrity data in DRAM
  benchmark_params="--use-integrity-verifier --metadata-cache-size=2048 --metadata-cache-assoc=8 --enable-cxl --dram-size=3GiB --cxl-size=2GiB --integrity-allocation-mode=DramOnly --cxl-as-main --atomic-from-start --no-dram-for-apps"
  outdir="m5out-integrityalloc-appcxl-integritydram"

elif [ "$1" == "app-cxl-integrity-cxl" ]; then
  # App data in CXL, Integrity data in CXL
  benchmark_params="--use-integrity-verifier --metadata-cache-size=2048 --metadata-cache-assoc=8 --enable-cxl --dram-size=0 --cxl-size=2GiB --integrity-allocation-mode=CxlOnly --cxl-as-main --atomic-from-start --no-dram-for-apps"
  outdir="m5out-integrityalloc-appcxl-integritycxl"

else
  echo "Invalid configuration. Valid options:"
  echo "- app-dram-integrity-dram"
  echo "- app-dram-integrity-cxl"
  echo "- app-cxl-integrity-dram"
  echo "- app-cxl-integrity-cxl"

  exit 1
fi

${gdb} ${gem5_binary} ${gem5_params} --outdir ${outdir} ${redirect} ${config_file} ${benchmark_params}

exit
}
