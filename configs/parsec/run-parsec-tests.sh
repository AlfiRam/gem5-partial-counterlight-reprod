#!/bin/bash
{

gem5_binary="./build/X86/gem5.opt"
config_file="configs/parsec/x86-parsec-ubuntu-22.py"
gem5_params="--listener-mode=on --debug-flags=CoherentXBar,MetadataCache"
# gem5_params="--debug-flags=MemCtrl,XBar"

resource_json_path="${HOME}/Documents/gem5-resources/resources-generated.json"
resource_build_path="${HOME}/Documents/gem5-resources/src/parsec/build-parsec-22-04"
kernel_path="${resource_build_path}/vmlinux-x86-ubuntu"
img_path="${resource_build_path}/parsec-22-04"

# benchmark_params="--benchmark blackscholes --size simdev --no-stop-after-roi"
benchmark_params="--benchmark blackscholes --size simdev"

# benchmarks=("blackscholes" "bodytrack" "canneal" "dedup" "facesim" "ferret" "fluidanimate" "freqmine" "raytrace" "streamcluster" "swaptions" "vips" "x264")

# for benchmark in "${benchmarks[@]}"; do
#   benchmark_params="--benchmark ${benchmark} --size simdev"

#   env GEM5_RESOURCE_JSON_APPEND=${resource_location} ${gem5_binary} ${gem5_params} --outdir m5out-simdev-${benchmark} ${config_file} ${benchmark_params} --kernel-path ${kernel_path} --img-path ${img_path} &
# done

env GEM5_RESOURCE_JSON_APPEND=${resource_location} ${gem5_binary} ${gem5_params} --outdir m5out ${config_file} ${benchmark_params} --kernel-path ${kernel_path} --img-path ${img_path} &

wait $(jobs -p)

exit
}
