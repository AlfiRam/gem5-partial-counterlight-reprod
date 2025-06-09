#!/bin/bash
{

# gem5_binary="./build/X86/gem5.opt"
gem5_binary="./build/X86/gem5.debug"
config_file="configs/integrity_verifier/basic-demo.py"
# gem5_params="--listener-mode=on"
gem5_params="--listener-mode=on --debug-flags=AbstractIntegrityVerifier,SimpleMetadataCache,TimingTree,MemCtrl,DRAM"

# redirect="--redirect-stdout --stdout-file stdout.txt --redirect-stderr --stderr-file stderr.txt"
redirect=""

benchmark_params="--use-integrity-verifier --metadata-cache-size=30000"
outdir="m5out-integrityverifiertest-demo"

${gem5_binary} ${gem5_params} --outdir ${outdir} ${redirect} ${config_file} ${benchmark_params}

exit
}
