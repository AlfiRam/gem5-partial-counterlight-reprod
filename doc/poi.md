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

Panics:

``` cpp
#include "base/logging.hh"
// Alternatively, this is included implicitly with "base/trace.hh".
```


## Create a New `SimObject`

Basic Python declaration for object:

``` py
from m5.params import *
from m5.SimObject import SimObject

class ObjectName(SimObject):
    type = "ObjectName"
    cxx_header = "directory_path/to/file.hh"
    cxx_class = "gem5::ObjectName"

    # Add params here...
    # For example:
    # parameter = Param.Int(default_value, "Description")
```

Basic C++ header for object:

``` cpp
// Suppose this is located at directory_path/to/file.hh
#ifndef __DIRECTORY_PATH_TO_FILE_HH__
#define __DIRECTORY_PATH_TO_FILE_HH__

#include "params/ObjectName.hh"
#include "sim/sim_object.hh"

namespace gem5
{

class ObjectName : public SimObject
{
  private:
    void processEvent();

    MemberEventWrapper<&ObjectName::processEvent> event;

  public:
    // Note that the ObjectNameParams class will be generated automatically,
    // and be placed in the included "params/ObjectName.hh" header file.
    ObjectName(const ObjectNameParams &p);

    void startup() override;
};

} // namespace gem5

#endif // __DIRECTORY_PATH_TO_FILE_HH__
```

Basic C++ code for object:

``` cpp
#include "directory_path/to/file.hh"

namespace gem5
{

ObjectName::ObjectName(const ObjectNameParams &params) :
  SimObject(params), event(*this)
{
  // Write constructor code here...
  // You can also set initial values with member initializer lists
}

void
ObjectName::processEvent()
{
  // Write code to process an event here...
}

void
ObjectName::startup()
{
  // Executed for any last initialization before the simulation starts.
  // For example, can be used to schedule some initial events to start.
  // schedule(...)
}

} // namespace gem5
```

Add to `SConscript` file:

``` py
Import("*")

SimObject("ObjectName.py", sim_objects=["ObjectName", ...])
Source("object_name.cc")
...
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


## Panics

Add import:

``` cpp
#include "base/logging.hh"
// Alternatively, this is included implicitly with "base/trace.hh".
```

Create panic statement:

``` cpp
// Unconditional panic:
panic("Description of the panic.");

// Conditional panic:
panic_if(condition, "Description of the panic.");

// For either of these, you can use printf() formatting.
```


## Building Extra Separate Vendor Code

> Source: https://www.gem5.org/documentation/general_docs/building/EXTRAS

You may want to be able to add code that is separate from the main `src/` directory, but still have it treated as though it were part of the same directory. This can be accomplished with an `EXTRAS` variable.

Consider the standard command to compile:

```
scons build/<ISA>/gem5.<BUILD_VARIANT> -j<CORES>
```

You can add another directory by adding an `EXTRAS` option like the following:

```
scons EXTRAS=path/to/directory build/<ISA>/gem5.<BUILD_VARIANT> -j<CORES>
```

Note that the `EXTRAS` option is "sticky," meaning that it will persist for any future builds that go to the same build directory. Override this by making it blank (`EXTRAS=`).

You can have multiple directories by separating with a colon:

```
scons EXTRAS=path/to/directory:path/to/other_directory build/<ISA>/gem5.<BUILD_VARIANT> -j<CORES>
```


## Parameters

Parameters are incredibly useful in gem5, as they allow you to tweak and adjust behavior to an object without recompiling.

### Basic Parameter Usage

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

### Parameter Types for Python `SimObject`s

*See `src/python/m5/params.py` for full source code.*

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

In addition to the provided types, you can use any other `SimObject` straightaway as a parameter, without additional code. In this case, use the Python class name in place of the `<TypeName>`, as written in the previous example.

### Using Parameters from Python in C++

Parameters can be defined within a `SimObject` class definition in Python, and further set within your Python config file. This section describes how you can bring values from the parameters in Python into C++ code, such that you can adjust functionality based on the parameters.

First, you will need to add the parameter to the Python class. For this example, a simple integer parameter will be used, but you can use any other type as desired.

``` py
# ...

class ObjectName(SimObject):
    # Define details about the object here...

    # Parameters
    # parameter_name = Param.<TypeName>([default_value, ]"Description")
    number_of_beans = Param.Int(5, "The number of beans that the object has")

    # Add more parameters as desired...
```

In this case, we have defined an integer parameter called `number_of_beans`, with a default value of 5.

If the parameter doesn't have a default value, or you would otherwise like to override the value, this is done in your Python config script:

``` py
# ...

my_object = ObjectName(number_of_beans=20)

# Alternatively...

my_object = ObjectName()
my_object.number_of_beans = 20

# ...
```

Finally, you will bring the parameter from Python into C++ using the class constructor.

> For a full example structure of how a class looks, see earlier in this document. This section is just focused on parameters.

Recall the general structure of the header file, including the constructor. To bring over the parameter in C++, you will likely also want to add a class member that can store the value. (Note that the name here does not need to match, but it can be the same for convenience.)

``` cpp
// ...

class ObjectName : public SimObject
{
  // ...

  private:
    int number_of_beans;

  public:
    ObjectName(const ObjectNameParams &p);

  // ...
};

// ...
```

Within the C++ code, you will then use the constructor to bring over the parameter.

This is then saved into a class member within C++ using a member initializer list.

``` cpp
// ...

ObjectName::ObjectName(const ObjectNameParams &params) :
  SimObject(params), number_of_beans(params.number_of_beans)
{
  // Write constructor code here...
}

// ...
```

Note that in this example, the Python parameter is referred to by `params.number_of_beans`. The name after "`params.`" will be the same as what is defined within the Python class.

Alternatively, if you have more complex logic, you could also write this within the constructor function body:

``` cpp
// ...

ObjectName::ObjectName(const ObjectNameParams &params) :
  SimObject(params)
{
  number_of_beans = params.number_of_beans;
}

// ...
```

Now you are free to use this `number_of_beans` variable anywhere in the class as needed.

### Enum Parameters

This section describes two things: (1) How to create an enum in Python and export it to C++, and (2) how to use a newly-created enum as a parameter for a `SimObject`.

First, you can define your enum anywhere you'd like. For simplicity, it will be defined in the same file as Python class. To define the enum, create a new Python class that derives the `Enum` class (from `src/python/m5/params.py`), and set a member `vals` to a list of strings representing all the enum values.

This is an example where we create an enum for some object's "speed mode." It can either be "fast" or "slow."

``` py
# Assume this is being written in the same place as the SimObject that will use the enum. (ObjectName.py for example.)
# ...

# Needed for the `Enum` object.
from m5.params import *

class SpeedMode(Enum):
    vals = ["fast", "slow"]

# ...
```

To allow the enum to be used as a parameter, thus being "translated" into C++, you will first need to export it to be compiled in your `SConscript` file:

``` py
SimObject("ObjectName.py", sim_objects=["ObjectName"], enums=["SpeedMode"])
```

Note the addition of the `enums` part of the `SimObject` function call.

> **Note:** While the function is called `SimObject`, you could technically define the enum in its own file in the same way. In this case, you can omit the `sim_objects` part and just have the `enums` part. If `SpeedMode` had been defined within its own file, it could look something like this:
>
> ``` py
> SimObject("SpeedMode.py", enums=["SpeedMode"])
> ```

Now that your enum is defined, you can use it as a parameter!

In your Python object, add the parameter in the same way you would with other parameter types:

``` py
# ...

class ObjectName(SimObject):
    # Define details about the object here...

    speed_mode = Param.SpeedMode("fast", "The speed of the object")

    # Add more parameters as desired...
```

Note that in Python, you write the enum parameter value as a string, based on the list of strings defined earlier. (Using a string that is not part of the list will result in an error.)

This is how it would look if you were setting the value from the Python config file:

``` py
# ...

my_object = ObjectName(speed_mode="slow")

# Alternatively...

my_object = ObjectName()
my_object.speed_mode = "slow"

# ...
```

To bring this over to the C++ side of the code, similar with other parameters, you will first likely want to define a new member variable to save it for use throughout the class:

``` cpp
// ...

// Note that for the case of a new enum, you will also need to include
// the corresponding C++ header, which is automatically generated during
// compilation. By default, the header will be in the `enums` folder and
// have the same name as the enum name.
#include "enums/SpeedMode.hh"

// ...

class ObjectName : public SimObject
{
  // ...

  private:
    enums::SpeedMode speed_mode;

  public:
    ObjectName(const ObjectNameParams &p);

  // ...
};

// ...
```

Then as with other parameters, you can copy the value from the generated C++ parameter object in the constructor:

``` cpp
// ...

ObjectName::ObjectName(const ObjectNameParams &params) :
  SimObject(params), speed_mode(params.speed_mode)
{
  // Write constructor code here...
}

// ...
```


## gem5 Common Functions

Within the gem5 library are some functions that may come in handy for a wide range of situations.

### In C++

- `curTick()`: Returns a copy of the current tick as a `Tick` object.
  - Defined in `src/sim/cur_tick.hh`
- `exitSimLoop(message[, exit_code])`: Schedule an event to exit the simulation loop. Returns the `message` string to Python to indicate why the simulation stopped. An exit code can also be optionally provided.
  - Defined in `src/sim/sim_exit.hh`
- `exitSimLoopNow(message[, exit_code])`: Schedule an event to exit the simulation loop, but with high priority so it runs before any normal events which are scheduled at the current time. Returns the `message` string to Python to indicate why the simulation stopped. An exit code can also be optionally provided.
  - Defined in `src/sim/sim_exit.hh`
- `schedule(event, when)`: Schedule an event `event` at some tick `when`.
  - Defined in `src/sim/eventq.hh`

## Statistics

To have statistics associated with your `SimObject`, you will override the `regStats()` function in your object's C++ header file:

``` cpp
class MyObject : public SimObject
{
  private:
    // ...

    statistics::Scalar stat1;
    // Add more statistics as desired...

  public:
    // ...

    void regStats() override;
};
```

Then add in the statistics upon saving the exported data by implementing `regStats()` in C++:

``` cpp
void
MyObject::regStats()
{
  // Call the superclass statistic registration first.
  SimObject::regStats();

  // Specify the name and description to identify this statistic.
  stat1
    .name(name() + ".stat1")
    .desc("Statistic description")
    .unit(statistics::units::InsertUnitTypeHere::get());

  // Additional statistics as desired...
}
```

### Common Statistic Types

*For all statistic data types, see `src/base/statistics.hh`.*

To use a statistic, you will first need to determine what type of data you are collecting. For example, this may be a single number or a collection of data points.

- `Scalar`: A simple counter based on the `double` C++ data type.
  - Can be incremented and decremented with with the standard `++` operator, for example.
- `Histogram`: A set of counters that are arranged in some initially-set number of buckets.
  - To use the `Histogram` type, you must also set the number of buckets for the variable:

      ```cpp
      histogramStat
        .name(name() + ".histogramStat")
        .desc("Statistic description")
        .init(<Number of buckets>)
        .unit(statistics::units::InsertUnitTypeHere::get());
      ```
- `Formula`: A formula that is calculated once statistics are printed.
  - After setting the name, description, and units of the statistic, you will also need to define the actual formula to be used:

      ```cpp
      formulaStat
        .name(name() + ".formulaStat")
        .desc("Statistic description")
        .unit(statistics::units::InsertUnitTypeHere::get());

      // Example
      formulaStat = (stat1 + stat2) / stat2;
      ```

### Common Statistics Unit Types

*For all unit types, see `src/base/stats/units.hh`.*

The unit type does not affect the calculation or organization of the statistic, but is more of an additional piece of information to more accurately describe a statistic.

- `Bit`: Represents the number of computer bits.
- `Byte`: Represents 8 bits.
- `Count`: Represents the count of a quantity not otherwise defined.
- `Cycle`: Represents clock cycles.
- `Rate<T1, T2>`: Represents the unit of a quantity of `T1` divided by a quantity of `T2`.
  - Typically used with the `Formula` type.
  - Example use (bits per second):

    ```cpp
    effectiveBandwidth
      .name(name() + ".effectiveBandwidth")
      .desc("Example statistic description (bits per second)")
      .unit(statistics::units::Rate<statistics::units::Bit, statistics::units::Second>::get());

    effectiveBandwidth = totalBits / executionTimeSeconds;
    ```
- `Second`: Represents the base unit of time defined by SI.
- `Tick`: Represents the count of gem5's `Tick`.
