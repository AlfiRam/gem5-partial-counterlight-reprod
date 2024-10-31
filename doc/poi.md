# Points of Interest

This document intends to list some information about where to find certain pieces of information that may otherwise be difficult to find quickly. Highlights will be provided here.

## Imports

### For Python

Extend a `SimObject`:

``` py
from m5.SimObject import SimObject
```

Create parameters in an object:

``` py
from m5.params import *
```

### For C++ Header

Extend a `SimObject`:

``` cpp
#include "sim/sim_object.hh"
```

Add parameters from Python side of code:

``` cpp
#include "params/<ObjectName>.hh"
```

### For C++ Code

Debugging functions (e.g., `DPRINTF`):

``` cpp
#include "base/trace.hh"
```

Debug tags (including new created ones):

``` cpp
#include "debug/<TagName>.hh"
```


## Create and Use Debugging Flag

Add to `SConscript` file:

``` py
DebugFlag("<TagName>")
```

Import in your C++ file of choice:

``` cpp
#include "base/trace.hh"       // For the DPRINTF, etc. functions
#include "debug/<TagName>.hh"
```

Create debugging statement:

``` cpp
DPRINTF(<TagName>, "My message with some value %d\n", value);
```


## Parameter Types for Python `SimObject`s

*See `src/python/m5/params.py` for full source code.*

First, import in Python with:

``` py
from m5.params import *
```

Add a parameter by:

``` py
# Without a default value
param_name = Param.<TypeName>("Description")

# With a default value
param_name = Param.<TypeName>(default_value, "Description")
```

Some example types:

- `Addr`: May be written as a value, or can be a size. For using a size, see `MemorySize` for some formatting details. Implemented as a 64-bit unsigned integer.
- `AddrRange`: Has a start and end value to specify a range of addresses. There are a few ways to initialize this:
  - With an array or tuple of two elements, or two parameters, giving the start and end of the range. `[start, end]` or `(start, end)` or `start, end`.
  - With one parameter, indicating the end of the range. The range implicitly starts at 0. `end`.
  - With one parameter, indicating the start of the range, and a kwarg of either "end" or "size", for an absolute or relative end address of the range. `start, end=end`, or `start, size=size`.
- `Bool`: Boolean value.
- `Counter`: Unsigned 64-bit integer.
- `Cycles`: Unsigned 64-bit integer.
- `Float`: 64-bit floating point value.
- `Frequency`: Indicates a value of frequency. Initialize with a string `<time>Hz`, where `<time>` is an integer, optionally followed by an SI suffix. For example, `"5kHz"` for 5,000 times per second. There is a difference between "Mi" (power of 2) and "M" (base-10) in this case.
- `Int`: Signed (32-bit) integer.
- `Int8`, `UInt8`: 8-bit integer. Signed/unsigned.
- `Int16`, `UInt16`: 16-bit integer. Signed/unsigned.
- `Int32`, `UInt32`: 32-bit integer. Signed/unsigned.
- `Int64`, `UInt64`: 64-bit integer. Signed/unsigned.
- `Latency`: Indicates a value of time for latency. There are a few ways to initialize this. Implemented as an integer for the case of ticks; implemented as a floating-point value for the case of seconds.
  - Write with a string `<time>t`, where `<time>` is an integer. This indicates latency in number of ticks.
  - Write with a floating-point value for time in seconds.
  - Write with a string `<time>s`, where `<time>` is an integer, optionally followed by an SI suffix. For example, `30us` for 30 microseconds. There is a difference between "Mi" (power of 2) and "M" (base-10) in this case.
- `MemoryBandwidth`: The value can be written as a string like "1MiB/s" and it will be converted to the corresponding value. This uses the power-of-2 version of the number ($2^{20} = 1024*1024 = 1,048,576$), not the base-10 version ($1*10^6 = 1,000,000$). Implemented as a floating-point value, representing the number of bytes per second.
- `MemorySize`: The value can be written as a string like "1MiB" and it will be converted to the corresponding value. This uses the power-of-2 version of the number ($2^{20} = 1024*1024 = 1,048,576$), not the base-10 version ($1*10^6 = 1,000,000$). Implemented as a 64-bit unsigned integer.
- `Percent`: Integer between 0 and 100.
- `String`: Just a string.
- `Tick`: Unsigned 64-bit integer.
- `Unsigned`: Unsigned (32-bit) integer.
