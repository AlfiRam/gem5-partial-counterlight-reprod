#!/bin/bash
{

gem5_binary="./build/X86/gem5.debug"
# gem5_binary="./build/X86/gem5.debug"
# config_file="configs/integrity_verifier/basic-demo-cxl.py"
# gem5_params="--listener-mode=on"
# gem5_params="--listener-mode=on --debug-flags=AbstractIntegrityVerifier,SimpleMetadataCache,TimingTree,MemCtrl,DRAM"
# gem5_params="--listener-mode=on --debug-flags=AbstractIntegrityVerifierTest"
# gem5_params="--listener-mode=on --debug-flags=AbstractIntegrityVerifierReqs,TimingTree,XBar,BaseXBar"
# gem5_params="--listener-mode=on --debug-flags=AbstractIntegrityVerifierReqs,TimingTree,CXLMemory,Exec,-ExecMicro"
# gem5_params="--listener-mode=on --debug-flags=IntegrityNodeLocationMap,AbstractIntegrityVerifierTest,IdeDisk"
# gem5_params="--listener-mode=on --debug-flags=AbstractIntegrityVerifierTest,TimingTree,MetadataCache"
gem5_params="--listener-mode=on --debug-flags=IntegrityVerifierAll,TimingTree,MetadataCache,MetadataCacheEviction"

# redirect="--redirect-stdout --stdout-file stdout.txt --redirect-stderr --stderr-file stderr.txt"
redirect=""

# benchmark_params="--use-integrity-verifier --metadata-cache-size=30000 --enable-cxl"
# benchmark_params="--use-integrity-verifier --metadata-cache-size=2048 --enable-cxl --dram-size=3GiB --cxl-size=4GiB --integrity-allocation-mode=CxlOnly"
# benchmark_params="--use-integrity-verifier --metadata-cache-size=2048 --enable-cxl --dram-size=0 --cxl-size=2GiB --integrity-allocation-mode=CxlOnly --cxl-as-main --timing-from-start"

# outdir="m5out-cxlintegrity-demo"
# outdir="m5out-integrityalloc-cxlonly"

if [ "$3" == "gdb" ]; then
  gdb="gdb --args"
elif [ "$3" == "gdbrun" ]; then
  gdb="gdb --eval-command run --args"
else
  gdb=""
fi


# benchmarks=("parsecblackscholes" "micropass" "microrandom")
# for benchmark in "${benchmarks[@]}"; do

selected_benchmark="$1"

if [ "$selected_benchmark" == "parsecblackscholes" ]; then
  config_file="configs/integrity_verifier/x86-parsec-ubuntu-22.py"
  resource_build_path="${HOME}/Documents/gem5-resources/src/custom-imgs/build-parsec-22-04"
  kernel_path="${resource_build_path}/vmlinux-x86-ubuntu"
  img_path="${resource_build_path}/parsec-22-04"
  benchmark="blackscholes"
  size="simmedium"
  benchmark_params="--benchmark ${benchmark} --size ${size} --kernel-path ${kernel_path} --img-path ${img_path}"

elif [ "$selected_benchmark" == "microshortpass" ]; then
  config_file="configs/integrity_verifier/x86-microbenchmarks-ubuntu-22.py"
  resource_build_path="${HOME}/Documents/gem5-resources/src/custom-imgs/build-microbenchmarks-22-04"
  kernel_path="${resource_build_path}/vmlinux-x86-ubuntu"
  img_path="${resource_build_path}/microbenchmarks-22-04"
  benchmark="widepass"
  benchmark_params="--benchmark ${benchmark} --page-size=4096 --page-count=10 --passes=30 --kernel-path ${kernel_path} --img-path ${img_path}"

elif [ "$selected_benchmark" == "micropass" ]; then
  config_file="configs/integrity_verifier/x86-microbenchmarks-ubuntu-22.py"
  resource_build_path="${HOME}/Documents/gem5-resources/src/custom-imgs/build-microbenchmarks-22-04"
  kernel_path="${resource_build_path}/vmlinux-x86-ubuntu"
  img_path="${resource_build_path}/microbenchmarks-22-04"
  benchmark="widepass"
  benchmark_params="--benchmark ${benchmark} --page-size=4096 --page-count=3000 --passes=2 --kernel-path ${kernel_path} --img-path ${img_path}"

elif [ "$selected_benchmark" == "microrandom" ]; then
  config_file="configs/integrity_verifier/x86-microbenchmarks-ubuntu-22.py"
  resource_build_path="${HOME}/Documents/gem5-resources/src/custom-imgs/build-microbenchmarks-22-04"
  kernel_path="${resource_build_path}/vmlinux-x86-ubuntu"
  img_path="${resource_build_path}/microbenchmarks-22-04"
  benchmark="widerandom"
  benchmark_params="--benchmark ${benchmark} --page-size=4096 --page-count=3000 --passes=200000 --kernel-path ${kernel_path} --img-path ${img_path}"

else
  echo "Invalid benchmark. Valid options:"
  echo "- parsecblackscholes"
  echo "- microshortpass"
  echo "- micropass"
  echo "- microrandom"

  exit 1
fi


selected_configuration="$2"

if [ "$selected_configuration" == "app-dram-integrity-dram" ]; then
  # App data in DRAM, Integrity data in DRAM
  benchmark_params="${benchmark_params} --use-integrity-verifier --metadata-cache-size=2048 --dram-size=3GiB --cxl-size=0 --integrity-allocation-mode=DramOnly"
  # outdir="m5out-integrityalloc-appdram-integritydram"

elif [ "$selected_configuration" == "app-dram-integrity-cxl" ]; then
  # App data in DRAM, Integrity data in CXL
  benchmark_params="${benchmark_params} --use-integrity-verifier --metadata-cache-size=2048 --enable-cxl --dram-size=3GiB --cxl-size=2GiB --integrity-allocation-mode=CxlOnly --no-cxl-for-apps"
  # outdir="m5out-integrityalloc-appdram-integritycxl"

elif [ "$selected_configuration" == "app-cxl-integrity-dram" ]; then
  # App data in CXL, Integrity data in DRAM
  # benchmark_params="${benchmark_params} --use-integrity-verifier --metadata-cache-size=2048 --enable-cxl --dram-size=3GiB --cxl-size=2GiB --integrity-allocation-mode=DramOnly --cxl-as-main --atomic-from-start --no-dram-for-apps"
  benchmark_params="${benchmark_params} --use-integrity-verifier --metadata-cache-size=2048 --enable-cxl --dram-size=3GiB --dram-os-size=256MiB --cxl-size=2GiB --integrity-allocation-mode=DramOnly"
  # outdir="m5out-integrityalloc-appcxl-integritydram"

elif [ "$selected_configuration" == "app-cxl-integrity-cxl" ]; then
  # App data in CXL, Integrity data in CXL
  # benchmark_params="${benchmark_params} --use-integrity-verifier --metadata-cache-size=2048 --enable-cxl --dram-size=0 --cxl-size=2GiB --integrity-allocation-mode=CxlOnly --cxl-as-main --atomic-from-start --no-dram-for-apps"
  benchmark_params="${benchmark_params} --use-integrity-verifier --metadata-cache-size=2048 --enable-cxl --dram-size=256MiB --dram-os-size=256MiB --little-dram --cxl-size=2GiB --integrity-allocation-mode=CxlOnly"
  # outdir="m5out-integrityalloc-appcxl-integritycxl"

else
  echo "Invalid configuration. Valid options:"
  echo "- app-dram-integrity-dram"
  echo "- app-dram-integrity-cxl"
  echo "- app-cxl-integrity-dram"
  echo "- app-cxl-integrity-cxl"

  exit 2
fi


outdir="output/testsuite/${selected_benchmark}_${selected_configuration}"
mkdir -p "$outdir"

${gdb} ${gem5_binary} ${gem5_params} --outdir ${outdir} ${redirect} ${config_file} ${benchmark_params}

exit
}
