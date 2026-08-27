# MatMul case study

This is a micro case study that applies Stomp to a simple matrix multiplication
benchmark, which uses OpenMP for GPU offload in two different ways: one using
simple loop directive, and the other using explicit threading in the style of
CUDA/HIP/OpenCL.

Running Stomp on the source file [gpu_mat_mul.F90](gpu_mat_mul.F90)

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

The loop uses a team of threads to load sub-matrices from global memory into
team-local memory before invoking a barrier and then reading the values from
team-local memory. The barrier separates the writes from the subsequent reads.
However, there is also a path from the reads back round to the writes, which is
not separated by a barrier. Adding an extra barrier after the read loop solves
the problem.
