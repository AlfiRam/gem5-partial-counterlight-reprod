# Counter-light Memory Encryption Reproduction

A gem5-based reproduction of Counter-light Memory Encryption (ISCA 2024), with extensions that quantify the cost of restoring replay protection on the read path.

## Based on

- **Base simulator**: gem5 v24.1.0.1.
- **Counter-light paper**: Wang et al., "Counter-light Memory Encryption," ISCA 2024.

## Requirements

Same as gem5. Recommended on Ubuntu 20.04 or 22.04:

```bash
sudo apt install build-essential git m4 scons zlib1g zlib1g-dev \
    libprotobuf-dev protobuf-compiler libprotoc-dev libgoogle-perftools-dev \
    python3-dev python-is-python3 libboost-all-dev pkg-config
```

KVM must be accessible on the host (`/dev/kvm`).

## Clone and build

```bash
git clone https://github.com/AlfiRam/gem5-counterlight-reprod.git
cd gem5-counterlight-reprod
scons build/X86/gem5.opt -j$(nproc)
```

## Kernel and disk image

The simulation requires a Linux disk image with GAPBS pre-installed and a matching x86 kernel. Both are too large for git and must be downloaded separately:

```bash
mkdir -p fs_files && cd fs_files
wget https://dist.gem5.org/dist/develop/images/x86/ubuntu-18-04/gapbs.img.gz
gunzip gapbs.img.gz
wget https://dist.gem5.org/dist/develop/kernels/x86/static/vmlinux-4.19.83
cd ..
```

Then update the hardcoded path in `configs/integrity_verifier/basic-demo.py` to point at your `fs_files/` directory:

```python
_FS_FILES = Path("/path/to/your/fs_files")
```

## Running a simulation

```bash
./build/X86/gem5.opt \
    --outdir=<output_directory> \
    configs/integrity_verifier/basic-demo.py \
    --workload <workload> \
    --ff-insts <fast_forward_instructions> \
    --exec-insts <timing_window_instructions> \
    --read-path-mode=<mode>
```

| Argument | Options | Description |
|----------|---------|-------------|
| `--outdir` | path | Where `stats.txt` is written |
| `--workload` | `bfs`, `sssp`, `pr` | GAPBS algorithm |
| `--ff-insts` | integer | KVM fast-forward instruction count |
| `--exec-insts` | integer | Timing window instruction count |
| `--read-path-mode` | `CounterLight`, `CounterLightBmt`, `CounterLightMacBmt` | Read-path strategy |

### Example

```bash
./build/X86/gem5.opt \
    --outdir=m5out-bfs-counterlight \
    configs/integrity_verifier/basic-demo.py \
    --workload bfs \
    --ff-insts 1000000000 \
    --exec-insts 500000000 \
    --read-path-mode=CounterLight
```

## Reading results

Key metrics from the Timing window are in `<output_directory>/stats.txt`. 
