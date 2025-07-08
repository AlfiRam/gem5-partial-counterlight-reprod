#!/bin/bash
{

gem5_binary="./build/X86/gem5.opt"
# gem5_binary="./build/X86/gem5.debug"
config_file="configs/integrity_verifier/x86-microbenchmarks-ubuntu-22.py"
# gem5_params="--listener-mode=on --debug-flags=AbstractIntegrityVerifier,SimpleMetadataCache,TimingTree,MemCtrl,DRAM"
gem5_params="--listener-mode=on"

resource_json_path="${HOME}/Documents/gem5-resources/resources-generated.json"
resource_build_path="${HOME}/Documents/gem5-resources/src/custom-imgs/build-microbenchmarks-22-04"
kernel_path="${resource_build_path}/vmlinux-x86-ubuntu"
img_path="${resource_build_path}/microbenchmarks-22-04"

# redirect="--redirect-stdout --stdout-file stdout.txt --redirect-stderr --stderr-file stderr.txt"
redirect=""

# benchmark="widepass"
# benchmark_params="--use-integrity-verifier --metadata-cache-size 30000 --benchmark ${benchmark} --page-size=4096 --page-count=3000 --passes=10"

benchmark="widerandom"
benchmark_params="--use-integrity-verifier --metadata-cache-size 30000 --benchmark ${benchmark} --page-size=4096 --page-count=3000 --passes=2"
outdir="m5out-microbenchmark-${benchmark}"
env GEM5_RESOURCE_JSON_APPEND=${resource_location} ${gem5_binary} ${gem5_params} --outdir ${outdir} ${redirect} ${config_file} ${benchmark_params} --kernel-path ${kernel_path} --img-path ${img_path}

wait $(jobs -p)

exit
}
