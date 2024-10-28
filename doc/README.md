# Personal gem5 Documentation

This folder aims to create a consolidated location of some of the important aspects of gem5 while going through the process of learning.

## Installing gem5

This assumes you are using Ubuntu 24.10 at this time.


- Clone this repository.
- Install dependencies.
  - (For Ubuntu 24.10.) `sudo apt install build-essential git m4 scons zlib1g zlib1g-dev libprotobuf-dev protobuf-compiler libprotoc-dev libgoogle-perftools-dev python-dev python`
- Build gem5.
  - For more information, see:
    - [Building gem5 (Documentation)](https://www.gem5.org/documentation/general_docs/building)
    - [Building gem5 (Learning gem5)](https://www.gem5.org/documentation/learning_gem5/part1/building/)
  - The general format of the command to build is: `scons build/<ISA>/gem5.<BUILD_VARIANT> -j<CORES>`
    - `ISA`: The ISA you want to build support for. You can also choose `ALL` to include all available ISAs, or `NULL` to include none.
    - `BUILD_VARIANT`: The variant of build you want, choosing more optimization or more debugging capability. The options for this are `debug`, `opt`, and `fast`, ranging from most debugging-oriented to most optimization-oriented.
    - `CORES`: The number of cores in your system. You can technically use less than this, but you will probably want to use as many cores as possible for faster build times.
  - For example, if you want to build for x86 support, a moderate amount of optimization, and your system has 6 cores, you may use a command like the following to build: `scons build/X86/gem5.opt -j6`
- Run gem5.
  - The general format of the command to run is: `./build/<ISA>/gem5.<BUILD_VARIANT> <SCRIPT>`
    - The `ISA` and `BUILD_VARIANT` values are the same as the build step.
    - `SCRIPT`: This is the Python script ("configuration") you want to run against gem5. This contains the specification of the system you want to simulate and the workload you are simulating. The rest of the source code in gem5 (particularly all the C++ code) is used to define the actual objects that you are instantiating and simulating with.

## Helper Makefile

> *Note:* Credit to this article by Sebastian Witowski for the idea of this concept. https://switowski.com/blog/i-like-makefiles/

For simple tasks, you may find the Makefile in the root directory of the project helpful. This essentially contains some aliases for simple gem5 operation. If you want to do something more advanced like using command-line arguments to pass to a given script, you will need to run the full name of the command yourself.

For example, the Makefile is configured so you can just use `make build` as an alias for `scons build/X86/gem5.opt -j6`. This configuration is specific to my needs, but you may choose to adjust this Makefile for something that suits you more.

Run `make` or `make help` to see the full list of commands provided.

## Points of Interest

See [Points of Interest](poi.md) for information on where are good places to look for certain aspects of coding.
