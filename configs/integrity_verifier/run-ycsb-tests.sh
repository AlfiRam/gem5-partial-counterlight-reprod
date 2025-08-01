#!/bin/bash
{

# gem5_binary="./build/X86/gem5.opt"
gem5_binary="./build/X86/gem5.opt"
config_file="configs/integrity_verifier/x86-ycsb-ubuntu-22.py"
# gem5_params="--listener-mode=on --debug-flags=AbstractIntegrityVerifier,SimpleMetadataCache,TimingTree,MemCtrl,DRAM"
gem5_params="--listener-mode=on"

resource_json_path="${HOME}/Documents/gem5-resources/resources-generated.json"
resource_build_path="${HOME}/Documents/gem5-resources/src/custom-imgs/build-ycsb-22-04"
kernel_path="${resource_build_path}/vmlinux-x86-ubuntu"
img_path="${resource_build_path}/ycsb-22-04"

# benchmark_params="--workload workloada"

# redirect="--redirect-stdout --stdout-file stdout.txt --redirect-stderr --stderr-file stderr.txt"
redirect=""


# benchmark=
# size=
# benchmark_params="--use-integrity-verifier --dram-size=3GiB --integrity-allocation-mode=DramOnly --workload workloada"
benchmark_params="--dram-size=3GiB --workload workloada"
outdir="m5out-ycsb-test"
env GEM5_RESOURCE_JSON_APPEND=${resource_location} gdb --eval-command run --args ${gem5_binary} ${gem5_params} --outdir ${outdir} ${redirect} ${config_file} ${benchmark_params} --kernel-path ${kernel_path} --img-path ${img_path} &

wait $(jobs -p)

exit
}
