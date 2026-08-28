# GPU benchmarks case study

This case study applies Stomp to a set of GPU benchmarks, which use OpenMP for
GPU offload in two main ways: one using simple loop directives, and the
other using explicit threads in the style of CUDA/HIP/OpenCL.

## Matrix multiplication

Running Stomp on [gpu_mat_mul.F90](gpu_mat_mul.F90)

```
▶ stomp gpu_mat_mul.F90
```

reveals two issues. The first

```
Issue: ScalarDataRace
Routine: mat_mul_simple
Directive: '!$omp target teams distribute parallel do collapse(2) !nowai'
Statement: 'acc = 0'
Description: Data race in parallel region. Thread (team=0,thread=0) and
thread (team=0,thread=1) have conflicting accesses to 'acc'.
```

is due to a missing `private` clause for the scalar variable `acc`. This is a
genuine issue, and easily fixed, though it's a bit unclear why the code seems
to function correctly in practice.

The second issue

```
Issue: ArrayDataRace
Routine: mat_mul_cl
Directive: '!$omp target teams distribute collapse(2) thread_limit(16*16'
Statement: 'block_a(x,y) = a(k_base + x,row_a_base + y)'
Description: Data race in parallel region. Thread (team=0,thread=0) and
thread (team=0,thread=1) have conflicting accesses to 'block_a(0,0)'.
```

is a bug that that was present when writing the first version of the benchmark
and took a while to track down (before Stomp existed). The problem lies in the
following loop.

```f90
  acc = 0
  do k_base = 1, size(a, 1), TILE_SIZE
    ! Write to team-local arrays 'a' and 'b'
    block_a(x, y) = a(k_base+x, row_a_base+y)
    block_b(x, y) = b(col_b_base+x, k_base+y)
    !$omp barrier

    ! Read from team-local arrays 'a' and 'b'
    do k = 0, TILE_SIZE-1
      acc = acc + block_a(k, y) * block_b(x, k)
    end do
  end do
end program
```

The loop uses a team of threads to load a sub-matrix from global memory into
team-local memory before invoking a barrier and then reading the values from
team-local memory. The barrier separates the writes from the subsequent reads.
However, due to the loop, there is also a path from the reads back round to the
writes, which does not contain a barrier. Adding an extra barrier after the
read loop solves the problem.

## Stencil computation

Running Stomp on [gpu_stencil.F90](gpu_stencil.F90)

```
▶ stomp gpu_stencil.F90
```

reveals two issues, again. The first 

```
Issue: ScalarDataRace
Routine: stencil_simple
Directive: '!$omp target teams distribute parallel do collapse(2) !nowai'
Statement: 'total = mat_in(x,y - 1) + mat_in(x - 1,y) + mat_in(x,y) + ma'
Description: Data race in parallel region. Thread (team=0,thread=0) and
thread (team=0,thread=1) have conflicting accesses to 'total'.
```

is due to another missing `private` clause (this time for the variable
`total`). The second

```
Issue: ArrayDataRace
Routine: stencil_cl
Directive: '!$omp target teams distribute collapse(2) thread_limit(32) p'
Statement: 'mat_out(originx + x,originy + y) = total / 4'
Description: Data race in parallel region. Thread (team=1,thread=1) and thread (team=0,thread=1) have conflicting accesses to 'mat_out(2,32)'.
```

is due to conflicting writes to `mat_out` coming from different teams (the
issue message shows that the team ids are different, not the thread ids). This
is due to an off-by-one error. Both issues are fixed with the following patch.

```diff
<     !$omp&       distribute parallel do collapse(2) &
---
>     !$omp&       distribute parallel do collapse(2) private(total) &
51c51
<           do y = 1, TILE_SIZE-1
---
>           do y = 1, TILE_SIZE-2
```

## Summary

Overall, we have applied Stomp to the following files.

 | File                                           | Directives | SMT queries |
 | ---------------------------------------------- | ---------- | ----------- |
 | [gpu_histogram.F90](gpu_histogram.F90)         | 23         | 6           |
 | [gpu_mat_mul.F90](gpu_mat_mul.F90)             | 12         | 2           |
 | [gpu_mat_mul_fixed.F90](gpu_mat_mul_fixed.F90) | 13         | 4           |
 | [gpu_motion_est.F90](gpu_motion_est.F90)       | 14         | 5           |
 | [gpu_stencil.F90](gpu_stencil.F90)             | 12         | 3           |
 | [gpu_stencil_fixed.F90](gpu_stencil_fixed.F90) | 12         | 3           |
 | [gpu_transpose.F90](gpu_transpose.F90)         | 12         | 3           |
 | Total                                          | 98         | 26          |

These files are all included in our integration tests (see [run.sh](run.sh)
and the associated [Makefile](Makefile)).
