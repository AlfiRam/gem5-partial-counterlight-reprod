#!/bin/bash
{

# gem5_binary="./build/X86/gem5.opt"
gem5_binary="./build/X86/gem5.debug"
config_file="configs/integrity_verifier/x86-parsec-ubuntu-22.py"
# gem5_params="--listener-mode=on --debug-flags=AbstractIntegrityVerifier,SimpleMetadataCache,TimingTree,MemCtrl,DRAM"
gem5_params="--listener-mode=on"

resource_json_path="${HOME}/Documents/gem5-resources/resources-generated.json"
resource_build_path="${HOME}/Documents/gem5-resources/src/custom-imgs/build-parsec-22-04"
kernel_path="${resource_build_path}/vmlinux-x86-ubuntu"
img_path="${resource_build_path}/parsec-22-04"

# benchmark_params="--benchmark blackscholes --size simdev --no-stop-after-roi"
# benchmark_params="--benchmark ${benchmark} --size ${size}"

# benchmarks=("blackscholes" "bodytrack" "canneal" "dedup" "facesim" "ferret" "fluidanimate" "freqmine" "raytrace" "streamcluster" "swaptions" "vips" "x264")
# benchmarks=("blackscholes" "bodytrack" "dedup" "facesim" "raytrace" "vips")

# redirect="--redirect-stdout --stdout-file stdout.txt --redirect-stderr --stderr-file stderr.txt"
redirect=""

# for benchmark in "${benchmarks[@]}"; do
#   size="simdev"
#   benchmark_params="--benchmark ${benchmark} --size ${size}"
#   outdir="m5out-${size}-${benchmark}"

#   echo "===> Starting '${benchmark}' benchmark with size '${size}'"

#   env GEM5_RESOURCE_JSON_APPEND=${resource_location} ${gem5_binary} ${gem5_params} --outdir ${outdir} ${redirect} ${config_file} ${benchmark_params} --kernel-path ${kernel_path} --img-path ${img_path} &
# done

benchmark="blackscholes"
size="simdev"
benchmark_params="--use-integrity-verifier --metadata-cache-size 30000 --benchmark ${benchmark} --size ${size}"
outdir="m5out-${size}-${benchmark}"
env GEM5_RESOURCE_JSON_APPEND=${resource_location} ${gem5_binary} ${gem5_params} --outdir ${outdir} ${redirect} ${config_file} ${benchmark_params} --kernel-path ${kernel_path} --img-path ${img_path} &

wait $(jobs -p)

exit
}
