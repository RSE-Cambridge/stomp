# CGYRO

This is a small case study that applies Stomp to
[CGYRO](https://github.com/gafusion/gacode), a medium-sized Fortran codebase
(around 20K LoC) developed by atomic energy researchers which heavily uses
OpenMP for GPU offload.

First, we clone the repo

```
▶ git clone https://github.com/gafusion/gacode
```

and move to the directory containing the CGYRO code:

```
▶ cd gacode/cgyro/src
```

Starting small
--------------

A good place to start is `cgryo_source.f90`, which is a small 68-line file
containing OpenMP directives.

```
▶ stomp cgyro_source.F90
Summary
Directives found: 2
Issues found: 0
SMT queries/timeouts: 3/0
All checks passed!
```

Stomp reports no issues, having found 2 OpenMP directives and launched 3 SMT
queries (none of which timed out).

Looking at the code in more detail, we see that CGYRO uses CPP macros to
control whether to use OpenMP/CPU directives (default), OpenMP/GPU directives,
or OpenACC directives.  To check the OpenMP/GPU directives, we define CGYRO's
`OMPGPU` macro using Stomp's `-D` flag

```
▶ stomp -D OMPGPU cgyro_source.F90
```

which returns the same output as before.

Resolving imported symbols
--------------------------

Moving on to the slightly larger 107-line `cgyro_shear_hammett.F90`

```
▶ stomp -D OMPGPU cgyro_shear_hammett.F90
```

Stomp reports:

```
Issue: UnresolvedFuncOrArray
Directive: '!$omp target teams distribute parallel do simd collapse(2) p'
Statement: 'call ic_c(ir - 1, it)'
Description: Unresolved function (or array) symbol 'ic_c' in parallel region. The reason for the resolution failure is: 'Failed to find the source code of the unresolved routine 'ic_c'. It may be being brought into scope from one of ['cgyro_globals', 'timer_lib']. You may wish to add the appropriate module name to the `RESOLVE_IMPORTS` variable in the transformation script.'. Additional source files can be loaded using the '-l' and '-L' flags.
```

It has found an array symbol in a parallel region that has not been resolved.
(Note that PSyclone mistakenly refers to this as a function symbol; this is
because function invocation and array indexing have identical syntax in
Fortran.) As the messages indicates, the symbol likely comes from the
`cgyro_globals` module. The issue can be fixed by adding the file containing
this module via Stomp's `-l` flag:

```
▶ stomp -D OMPGPU -l cgyro_globals.F90 cgyro_shear_hammett.F90
Modules loaded: cgyro_globals
Modules not loaded: iso_c_binding, iso_fortran_env

Summary
Directives found: 2
Issues found: 0
SMT queries/timeouts: 4/0
All checks passed!
```

Multiple `-l` options can be provided to load multiple files, if required.

Adding Stomp directives
-----------------------

We can continue in the above fashion and sucessfully check the vast majority of
CGYRO source files. However, Stomp reports data races in
`cgyro_nl_comm.F90` including, for example:

```
Issue: ArrayDataRace
Routine: cgyro_nl_fftw_comm1_f64_async
Directive: '!$omp target teams distribute parallel do simd collapse(4) p'
Statement: 'fpacka(ir,itor - nt1 + 1,iexch_base + isplit0) = h_loc'
Description: Data race in parallel region. Thread (team=0,thread=0) and thread (team=0,thread=1) have conflicting accesses to 'fpacka(1,1,3)'.
```

A closer look at the source code reveals some implicit assumptions in the code.
Making these assumptions explicit via Stomp directives, as shown in this
[diff](https://github.com/mn416/gacode/commit/5150a6174472672de458a2a1ed8de677f7b1f818),
resolves the issues. These assumptions are likely valid, but that would be
best confirmed by the CGYRO developers.

Summary
-------

Overall, at the time of writing, we have checked the following CGYRO files.

  | File                               | Directives | SMT queries |
  | ---------------------------------- | ---------- | ----------- |
  | `cgyro_source.F90`                 | 2          | 3           |
  | `cgyro_shear_hammett.F90`          | 2          | 4           |
  | `cgyro_globalshear.F90`            | 2          | 1           |
  | `cgyro_init_h.F90`                 | 5          | 5           |
  | `cgyro_init_collision_landau.F90`  | 12         | 11          |
  | `cgyro_math.F90`                   | 36         | 21          |
  | `cgyro_parallel_lib.F90`           | 50         | 3           |
  | `cgyro_step_collision.F90`         | 22         | 10          |
  | `cgyro_rhs.F90`                    | 8          | 6           |
  | `cgyro_nl_comm.F90`                | 34         | 18          |
  | `cgyro_error_estimate.F90`         | 4          | 1           |
  | `cgyro_init_arrays.F90`            | 16         | 12          |
  | `cgyro_zftest_em.f90`              | 10         | 3           |
  | Total                              | 203        | 98          |

The only file we've been unable to check is `cgyro_nl_fftw.F90`, which contains
a Fortran `include` statement, not yet supported by Stomp.

Some of the larger files are included in our integration tests (see
[run.sh](run.sh)).
