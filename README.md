# Stomp

Stomp is a static checker for Fortran OpenMP directives based on
[PSyclone](https://github.com/stfc/PSyclone) (a Python library for processing
Fortran code developed by Met Office partners) and
[Z3](https://github.com/z3prover/z3) (a theorem prover from Microsoft
Research). It supports a subset of OpenMP 4.5 and Fortran 2003, and
solves 136 out of 166 problems from the
[DataRaceBench](https://github.com/llnl/dataracebench) benchmark suite.

## Contents

* [Installation](#installation)
* [Examples](#examples)
* [Supported Constructs](#supported-constructs)
* [Usage](#usage)
* [Stomp Directives](#stomp-directives)
* [Limitations](#limitations)

## Installation

The package has not yet been uploaded to PyPI. For now, download using `git`

```
▶ git clone --recursive https://github.com/rse-cambridge/stomp
```

and install locally with `pip3`:

```
▶ pip3 install ./stomp
```

## Examples

Consider the file
[examples/prefix_sum_chunks.f90](examples/prefix_sum_chunks.f90):

```f90
! Compute the prefix sums of chunks of the given array
! (a first step to computing the full parallel prefix sum)
subroutine prefix_sum_chunks(arr)
  integer, intent(inout) :: arr(:)
  integer :: chunk_size, chunk_begin, chunk_end, acc

  !$omp parallel
    ! The number of chunks is equal to the number of threads
    !$omp single
      chunk_size = omp_get_num_threads() / size(arr)
    !$omp end single

    ! Compute the prefix sum of each chunk
    !$omp do private(chunk_end, acc)
    do chunk_begin = 1, size(arr), chunk_size
      chunk_end = min(chunk_begin+chunk_size, size(arr))
      acc = 0
      do i = chunk_begin, chunk_end
        acc = acc + arr(i)
        arr(i) = acc
      end do
    end do
  !$omp end parallel
end subroutine
```

Running this file through Stomp

```
▶ stomp examples/prefix_sum_chunks.f90
```

produces:

```
Issue: ArrayDataRace
Routine: prefix_sum_chunks
Directive: '!$omp parallel'
Statement: 'arr(i) = acc' (line 20)
Description: Data race in parallel region. Thread 15 and thread
0 have conflicting accesses to 'arr(3)'.
```

The checker finds an off-by-one error in the calculation of `chunk_end`
allowing parallel writes to the same element of the shared array `arr`, which
is undefined behaviour in OpenMP.

For more examples, see the [examples](examples/) directory.

## Supported Constructs

Stomp has an understanding of the following OpenMP constructs.  Other
constructs are currently ignored.

  | Directives      | Clauses         | Functions               |
  | --------------- | --------------- | ----------------------- |
  | `target`        | `shared`        | `omp_get_thread_num()`  |
  | `teams`         | `private`       | `omp_get_team_num()`    |
  | `distribute`    | `firstprivate`  | `omp_get_num_threads()` |
  | `parallel`      | `lastprivate`   | `omp_get_num_teams()`   |
  | `do`            | `reduction`     |                         |
  | `barrier`       | `default`       |                         |
  | `atomic`        | `schedule`      |                         |
  | `critical`      | `collapse`      |                         |
  | `single`        | `nowait`        |                         |
  | `master`        | `num_threads`   |                         |
  | `threadprivate` | `num_teams`     |                         |
  | `sections`      | `thread_limit`  |                         |
  | `section`       |                 |                         |

## Usage

Typical steps:

1. **Check**. Apply the checker to a single source file of interest.  Strictly
speaking, the user should first ensure that the source file compiles without
error using a regular Fortran compiler; Stomp catches syntax errors by itself
but assumes that source code is well formed/typed. If the code requires
preprocessing, include paths can be specified with `-I` and macros
can be defined with `-D`.

2. **Add Dependencies**. Stomp may report unresolved symbols and ask for
additional source files in order to resolve them. This can be done using
`-l <FILENAME>` (to load a specified source file) or `-L <PATH>` (to load
all source files in a specified directory). 

3. **Resolve Issues**. Stomp often reports genuine bugs. However, it sometimes 
reports false positives, i.e. issues that the user knows are impossible in
an actual run of the program. A key feature of Stomp is that it allows the user
to resolve these false positives by adding `!$stomp` directives to the
code (see [Stomp Directives](#stomp-directives)). These directives allow the
programmer to specify (and document) their assumptions, and to use the checker
to ensure that the code is indeed safe under these assumptions.

When satisified, Stomp will report `All checks passed!`.  It can also
suggest loops for parallelisation, which are not already annotated with OpenMP
directives, when the `--infer` flag is provided.

For more detailed usage information, run `stomp --help`.

## Stomp Directives

Custom `!$stomp` directives are provided to help discharge false positives by
allowing various assumptions and abstractions to be specified.

### Logical Assumptions

The directive `!$stomp assume(<expr>)` tells Stomp to assume that the Fortran
expression `<expr>` evaluates to `.true.`. In the following example, the
parallel loop contains a data race only if `offset` is less than or equal to
`n`. This possibility is ruled out by the addition of the directive `!$stomp
assume (offset > n)` and, as a result, Stomp reports no data races.

```f90
subroutine sub(arr, offset, n)
  integer, intent(inout) :: arr(:)
  integer, intent(in) :: n, offset
  integer :: i
  !$stomp assume (offset > n)
  !$omp parallel do
  do i = 1, n
    arr(i) = 0
    arr(offset+i) = 1
  end do
end subroutine
```

Note that `!$stomp assume (offset > n)` could be replaced with

```f90
if (.not. offset > n) stop "Assumption broken"
```

This will also satisfy Stomp, which understands that any code following this
statement is only reachable if the assumption holds. In many cases, this is
preferable to an `assume` directive because it will raise a helpful runtime
error.

### Thread-Unique Values

The directive `!$stomp unique(<expr>)` tells Stomp that the Fortran expression
`<expr>` never evaluates to the same integer value in different threads.  In
the following example, array indices are obtained via a lookup table stored in
memory. Without the directive, Stomp would not be able to determine that
parallel accesses using these indices are non-conflicting.

```f90
subroutine sub(arr, lookup_table)
  integer, intent(inout) :: arr(:)
  integer, intent(in) :: lookup_table(:)
  integer :: i, j
  !$omp parallel do private(j)
  do i = 1, size(arr)
    j = lookup_table(i)
    !$stomp unique(j)
    arr(j) = 1
  end do
end subroutine
```

### Exclusive Regions

The directive `!$stomp exclusive` instructs Stomp that a region of code can be
assumed to be reachable by at most one thread. To illustrate, a minor variant
of the previous example:

```f90
subroutine sub(arr, lookup_table)
  integer, intent(inout) :: arr(:)
  integer, intent(in) :: lookup_table(:)
  integer :: i, j
  !$omp parallel do private(j)
  do i = 1, size(arr)
    j = lookup_table(i)
    if (j == 1) then
      !$stomp exclusive
      arr(j) = 1
      !$stomp end exclusive
    end if
  end do
end subroutine
```

### Thread-Safe Functions/Subroutines

By default, Stomp will only allow calls to `pure` subroutines/functions in a
parallel context.  The `!$stomp threadsafe(<name>)` directive can be used to
specify that a given subroutine/function is safe to call in parallel.  Similar
to OpenMP's `threadprivate` directive, this directive must appear in the
specification part of the Fortran module (i.e. before the `contains` keyword)
in which that subroutine/function is defined. Here is a simple example:

```f90
module example
  integer :: x
  !$omp threadprivate(x)
  !$stomp threadsafe(sub)
contains
  subroutine sub()
    x = 0
  end subroutine

  subroutine main()
    !$omp parallel
    call sub()
    !$omp end parallel
  end subroutine
end module
```

Currently, Stomp does not check that a routine marked as `threadsafe` is indeed
thread safe, which is a goal for future versions. There is also a command-line
flag `--threadsafe <name>` to signify that calls to the given
subroutine/function can be assumed to be thread safe.

### Abstracting Over Code Blocks

The `!$stomp abstract` directive instructs Stomp not to analyse a region of
code and supports `read`, `write`, and `readwrite` clauses to specify which
memory locations are accessed by the region.  

PSyclone does not currently have complete coverage of the Fortran language in
its intermediate representation -- see [Limitations](#limitations). For
example, `print` statements are not accurately represented. However, we can
tell Stomp how to handle it using an `abstract` region:

```f90
subroutine sub(n)
  integer, intent(in) :: n
  integer :: i
  !$omp parallel do
  do i = 1, 10
    !$stomp abstract read(n)
    print *, "Hello", n
    !$stomp end abstract
  end do
end subroutine
```

## Limitations

In general, Stomp aims to inform the user of its own limitations as it
encounters them. However, it's useful to be aware of the following.

* General nested parallelism is not supported, e.g. `parallel` directives
  which themselves contain `parallel` directives.  However,
  `parallel` directives nested within `teams` directives are a form of
  nested parallelism that _is_ very much supported.

* Stomp's understanding of OpenMP directives is incomplete -- see
  [Supported Constructs](#supported-constructs). Notable
  omissions include `task`, `workshare`, `target data`, and `target update`
  directives. These directives, some of which would require inter-procedural
  analysis, are being considered for future versions.

* The PSyclone intermediate representation is incomplete: some
  Fortran constructs, such as `print` statements and `block` statements,
  get represented as so-called `CodeBlock`s. When analysing a `CodeBlock`,
  PSyclone assumes the worst, e.g. all variables referenced inside the block
  are considered to be read and written. This can lead to unnecessary
  false positives. The `!$stomp abstract` directive can be used to abstract
  over blocks of code that PSyclone does not understand -- see
  [Stomp Directives](#stomp-directives).

* PSyclone and Stomp do not yet have good support for Fortran pointers.
  Stomp will, for example, treat a pointer to array in much
  the same way it would treat an array -- completely ignoring
  the possibility of aliasing. It may also struggle to resolve calls
  to subroutines/functions with pointer arguments.

## Acknowledgements

Thanks to Luke Abraham, Aidan Chalk, Chris Edsall, Joerg Henrichs, Andy Porter,
Sergi Sisso, Joe Wallwork, and Rob Waters. We also acknowledge the Met Office
funded NG-ARCH and NG-R2C projects where this tool originated.
