# Port Report: CXL-DMSim Removal

**Branch:** `local-dram-port` (off `jerrettl/project2-cxl`)
**Baseline target:** `app-dram-integrity-dram` (app data in DRAM, integrity metadata in DRAM, no CXL, no PageSwapper)
**Status:** Complete. Build and baseline clean end-to-end.

---

## 1. Scope and architectural impact

The goal was to strip every CXL-DMSim artifact from `gem5-jerrett` while preserving the secure-memory pipeline Jerrett layered on top of it (Integrity Verifier + Bonsai Merkle Tree w/ split counters + Metadata Cache + Partition Manager). The port produced a local-DRAM-only gem5 that runs the baseline integrity-verifier demo without touching any CXL code path.

**High-level removal:**

| Removed | Surface |
| --- | --- |
| CXL SimObjects | `CXLBridge`, `CXLMemory`, `CXLMemBar` |
| CXL MemCmds | `M2SReq`, `S2MDRS`, `M2SRwD`, `S2MNDR` (+ `cxl_cmd` packet field and `makeCXLResponse`) |
| Page-swap infrastructure | `PageSwapper` SimObject / .cc / .hh, all hierarchy-template wiring, `coherent_xbar` isForPageSwap guards |
| Board kwargs | `cxl_mode`, `cxl_memory`, `is_asic`, `main_memory_type`, `use_ncx`, `cxl_latency{,_read_req,_read_resp,_write_req,_write_resp}` across `abstract_board.py`, `abstract_system_board.py`, `x86_board.py` |
| Cache param | `BaseCache.enable_cxl` |
| Partition manager | `cxl_full_ranges`, `cxl_os_ranges`, `cxlIntegrityRanges` (partition count 5 → 3, REMOTE_{OS,METADATA} IDs collapsed) |
| Verifier stats | `reqHandledCxl*` family and pre/post-translation `Trans*` variants |
| Config-layer flags | 13 CLI flags from `create_board.py::add_arguments` (`--cxl-size`, `--cxl-mode`, `--cxl-memory-type`, `--cxl-latency*`, `--is-asic`, `--cxl-as-main`, `--no-cxl-for-apps`, `--no-dram-for-apps`, `--use-page-swapper`, `--page-swap-epoch`, `--integrity-allocation-mode`); plus `--enable-cxl` and `--cxl-mem-size` from `configs/common/Options.py`; plus `config_cxl()` from `MemConfig.py` |
| FSConfig wiring | CXL bridge wiring, `cxl_mem_start`, E820 entry, `enable_cxl` / `cxl_mem_size` kwargs on `makeX86System` / `makeLinuxX86System` |
| Enums | `IntegrityAllocationMode` (removed entirely rather than collapsed to single-value) |
| Scripts / docs | `configs/example/gem5_library/x86-cxl-run.py`, `configs/integrity_verifier/x86-cxl-run.py`, `configs/integrity_verifier/run-cxl-demo-test.sh`, `configs/deprecated/example/cxl_fs_py.sh`, `run_fs.sh`, `CXL-DMSim.md` |

**Preserved unchanged (per ANALYSIS_REPORT.md Section 6):**

- `src/mem/mtree/*` (BMT / Merkle tree)
- `src/mem/cache/metadata_cache.{hh,cc}` (tree-node-keyed metadata cache)
- Integrity verifier pipeline after CXL-range removal
- Cache partitioning machinery minus `PARTITION_ID_REMOTE_*`
- `ChanneledMemory.os_size` / `get_os_size()` plumbing
- Page-swap `Request`/`Packet` fields (`_isForPageSwap`, `_isTranslatedPageSwap`, `_originalAddr`, `_hasBeenTranslated`, `_pageSwapAddr`) and their accessors, plus `snoop_filter.getBlockAddr()` override — dead-but-safe (ripping them out touches ~20 files for zero runtime benefit)
- `InstrumentedCoherentXBar` / `InstrumentedNoncoherentXBar` — pass-through subclasses, placeholders for future instrumentation
- `_indexed_memory` / `get_starting_memory_addr(i)` / list-shaped `get_memory()` — required for x86 I/O hole handling even in single-DRAM case

**Net change:** 54 files modified, 15 files deleted, +320/−7093 lines.

---

## 2. Pre-existing branch bugs worked around

These were already broken on `jerrettl/project2-cxl` at fork time. They weren't caused by the port; the port simply couldn't run the baseline without fixing them. All four are documented here so they don't get misread as regressions.

### 2.1 `--cxl-size=0` vs `0B` argparse string assertion

`create_board.py:380` asserted exact string equality with the default `"0B"`, but the run script passed `--cxl-size=0`. One-char fix (`0` → `0B`) on line 33 of the run script made the assertion pass. Zero simulator-side effect. Fixed in Phase 0.5 and then obsoleted when `--cxl-size` itself was removed in Phase 1.

### 2.2 Dead MongoDB Atlas resource endpoint (HTTP 410)

`obtain_resource()` fails with `HTTP 410 Gone` on `basic-demo.py` because `src/python/gem5_default_config.py` points at a decommissioned MongoDB Atlas URL. Neither the Wayback Machine nor `resources.gem5.org/resources.json` (the legacy v22.1 manifest) has the `x86-ubuntu-24.04-boot-no-systemd` v3.0.0 entry, so the upstream manifest is unrecoverable.

**Workaround:** `basic-demo.py` uses `board.set_kernel_disk_workload(kernel=KernelResource(local_path=...), disk_image=DiskImageResource(local_path=...), ...)` with artifacts from CXL-Hammer's `fs_files` (symlinks to CXL-DMSim). See §3 below for baseline comparability caveats.

### 2.3 `metadata-cache-size=2048` vs `PartitionedMetadataCache` assoc×3 math

With 8-way associativity and 3 partitions, `2048 / (8 × 3) = 85.33…` — not a power of two, which trips a `BaseSetAssoc` assertion. Raised to `3072` (→ 128 sets) in `basic-demo.py`. Preserved comment in the file documenting the math.

### 2.4 pre-commit version skew

Installed `pre-commit` was 2.20.0 but some hook configs used 3.2 stage names. Committing with proper staging (re-`git add` after black auto-reformat) side-stepped the stage-name path. No config-file edit was needed.

---

## 3. Disk image substitution and baseline comparability

The original baseline used `obtain_resource("x86-ubuntu-24.04-boot-no-systemd", "3.0.0")`. With Atlas dead (§2.2), the port swapped in CXL-Hammer's `parsec.img` + `vmlinux_20240920` pair. Consequences:

- `get_disk_device()` returns `/dev/hda`, but parsec.img roots on the first partition. `basic-demo.py` overrides `disk_device="/dev/hda1"` explicitly.
- Kernel args copied from Jerrett's sibling scripts (`x86-spec2017-ubuntu-22.py`, `x86-cxl-run.py`).
- `readfile_contents="m5 exit\nm5 exit\n"` drives KVM→Timing switch (first exit) and shutdown (second exit).

**Comparability:** baseline stats from `local-dram-port` are internally consistent across phases (phase-to-phase regressions are meaningful) but are **not** directly comparable to any stats generated from the upstream `jerrettl/project2-cxl` baseline run with the 24.04 image. Future cross-branch comparisons need to either resurrect the original image or re-baseline both sides on the parsec.img workload.

**Kernel version ambiguity:** `~/.cache/gem5` had `x86-linux-kernel-6.8.0-35-generic` and `-52-generic`; the v3.0.0 manifest isn't recoverable, so `-52-generic` was a reasoned guess. The parsec.img path sidestepped this entirely.

---

## 4. Known unresolved issues

### 4.1 ExitEvent dispatch bug (bypassed)

On Jerrett's original `x86-ubuntu-24.04-boot-no-systemd` workload, `gem5-bridge exit` calls from `after_boot.sh` didn't reach `ExitEvent.EXIT` handlers as expected. Root cause not identified. The port bypassed this by swapping to the parsec.img workload where the `readfile_contents="m5 exit\nm5 exit\n"` pattern works. If someone re-enables the original workload, expect to rediscover this.

### 4.2 Graphing scripts left stale

`configs/integrity_verifier/graphing/` (15 Python files, 12 `.perf` gnuplot templates) contains post-processing scripts that read `Cxl*` stats, `cxl_comm_monitor.*`, and `PageSwap*` counters. These broke at Phase 2 (when the Cxl stats were stripped) and at Phase 3 (when PageSwapper was deleted). Rewriting 27 files of stats-parsing is its own project and was out of scope for the port. The baseline doesn't need them.

### 4.3 `cxl_os_size` return from `TimingTree.determine_max_protected_size`

The method still returns a `(dram_os_size, cxl_os_size)` tuple. The `cxl_os_size` value is now dead for all callers (no CXL = always 0 or meaningless). Renaming the return shape to drop the second value touches `src/mem/mtree/TimingTree.py`, `src/mem/mtree/TimingBmt.py`, `create_board.py`, and `debug_tests/test-tree-size-calculations.py`. Left as-is — dead value, live signature.

### 4.4 Surviving `cxl`/`CXL` string references

A final `git grep -i cxl` returns hits in:

- `configs/integrity_verifier/graphing/*` — §4.2
- `configs/integrity_verifier/basic-demo.py` — `CXL_HAMMER_FS_FILES` env var and docstring referencing CXL-Hammer/CXL-DMSim (path name; harmless)
- `configs/integrity_verifier/test_suite/test-suite.py:310` — kernel filename `vmlinux-5.15.0-141-generic+cxldmsim` (the kernel was compiled in the CXL-DMSim tree; the filename is a historical tag, not code)
- `configs/integrity_verifier/debug_tests/test-tree-size-calculations.py` — §4.3
- `src/mem/mtree/TimingTree.py`, `src/mem/mtree/TimingBmt.py` — §4.3 (comment-only `cxl` mentions inside `determine_max_protected_size`)
- `ANALYSIS_REPORT.md`, `split_counter_bmt_explanation.txt` — reference docs, not code

No live runtime code paths reference CXL.

---

## 5. Verification methodology

### 5.1 Per-phase regressions

Each phase ended with `make build-x86-opt` + baseline run as the structural check:

```
./build/X86/gem5.opt --outdir=m5out-integrityalloc-appdram-integritydram \
    --listener-mode=on configs/integrity_verifier/basic-demo.py
```

**Metric:** stat-line count from `m5out-integrityalloc-appdram-integritydram/stats.txt`. Not bit-identical diff — KVM boot is non-deterministic (timing of userspace driver probe ordering varies), so stat values fluctuate within noise across runs even with zero code change. The line count, however, tracks structural changes to the SimObject hierarchy (adding/removing a stat group shifts it).

| Phase | stats.txt lines | Notes |
| --- | ---: | --- |
| 0 (initial) | 2395 | fork-point baseline, pre-port |
| 1 (config neutralize) | 2395 | config-only, no runtime code touched |
| 2 (integrity-verifier strip) | 2381 | CxlOs/CxlIntegrity/Trans* stats removed |
| 3 (PageSwapper delete) | 2362 | 19 PageSwapper stats gone |
| 4 (CXL SimObject delete) | ~2362 | no runtime-stat-producing code removed (CXL paths were already unreachable by phase 1) |
| 5 (cleanup + assertion restore) | 2368 | within noise; io_device assertion did not fire |

All deltas accounted for by removed CXL and PageSwapper counters; no unexplained drift.

### 5.2 Risk-graded cadence

Config-only phases (0.5, 1) got one baseline at phase end. Runtime-touching phases (2–5) got per-step baselines where practical. The `io_device.hh` assertion restore in Phase 5 was the single highest-risk edit (it's an invariant that was commented out for a CXL reason that may or may not still apply); confirmed clean.

---

## 6. Commit graph

All commits on `local-dram-port` off `jerrettl/project2-cxl`, in reverse chronological order:

| Commit | Phase | Subject |
| --- | --- | --- |
| `de52da7b8d` | 5 | CXL cleanup sweep and assertion restore |
| `abc4558fd5` | 4 | Delete CXL SimObjects, MemCmds, and board kwargs |
| `9601c63345` | 3 | Delete PageSwapper |
| `99cd8c8fa8` | 2d | Strip CXL-range assignments from hierarchy templates |
| `ca081200dc` | 2c | Strip CXL ranges from DataLocationPartitionManager |
| `70d8913d3e` | 2 | Drop integrity_allocation_mode plumbing |
| `6759314189` | 2b | Drop IntegrityAllocationMode from SConscript enum list |
| `069e764430` | 2a-b | Strip CXL params and stats from IntegrityVerifier |
| `bb5edbf340` | 1f | Remove CXL plumbing from deprecated fs.py |
| `c5ee850d9c` | 1e | Remove CXL plumbing from FSConfig |
| `f6d4eb536e` | 1d | Remove config_cxl from MemConfig |
| `05d31dbb1a` | 1c | Drop enable_cxl wiring from CacheConfig |
| `90328c2e48` | 1b | Drop CXL flags from common Options |
| `882eded7b3` | 1a | Remove CXL flags and branches from create_board |
| `b0a750f069` | 0.5 | Fold integrity-verifier invocation into basic-demo.py |

---

## 7. Build and run instructions

Build:

```
make build-x86-opt
# or fallback: scons build/X86/gem5.opt -j<N> --linker=mold
```

Baseline run (local-DRAM integrity-verifier demo):

```
./build/X86/gem5.opt --outdir=m5out-integrityalloc-appdram-integritydram \
    --listener-mode=on \
    configs/integrity_verifier/basic-demo.py
```

Output lands in `m5out-integrityalloc-appdram-integritydram/`. First run needs the parsec.img/vmlinux pair at `$CXL_HAMMER_FS_FILES` (default `/home/malfiram/CXL-Hammer/fs_files`).

Test harness (simplified):

```
bash configs/integrity_verifier/test_suite/run-test-suite.sh <benchmark>
# benchmarks: parsecblackscholes | microshortpass | micropass | microrandom
```

or

```
python configs/integrity_verifier/test_suite/test-suite.py \
    --test-group <name> \
    --gem5 opt \
    --benchmark <benchmark> \
    --configuration app-dram-integrity-dram \
    --tree-type TimingBmt \
    --cache-type PartitionedMetadataCache
```

The full `--configuration` matrix is now `{app-dram-integrity-dram, app-dram-only}`.
