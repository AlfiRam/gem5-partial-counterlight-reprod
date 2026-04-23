#!/bin/bash
{

gem5_binary="./build/X86/gem5.debug"
gem5_params="--listener-mode=on --debug-flags=IntegrityVerifierAll,TimingTree,MetadataCache,MetadataCacheEviction"

redirect=""

if [ "$2" == "gdb" ]; then
  gdb="gdb --args"
elif [ "$2" == "gdbrun" ]; then
  gdb="gdb --eval-command run --args"
else
  gdb=""
fi


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


benchmark_params="${benchmark_params} --use-integrity-verifier --metadata-cache-size=2048 --dram-size=3GiB"

outdir="output/testsuite/${selected_benchmark}"
mkdir -p "$outdir"

${gdb} ${gem5_binary} ${gem5_params} --outdir ${outdir} ${redirect} ${config_file} ${benchmark_params}

exit
}
