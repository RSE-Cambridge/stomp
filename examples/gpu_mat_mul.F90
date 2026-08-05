! Tile size for optimised version
#define TILE_SIZE 16

module mat_mul_kernels
  use omp_lib

contains

  ! Simple untiled version
  subroutine mat_mul_simple(a, b, c, width_a, height_a, width_b)
    integer, intent(in) :: a(:,:), b(:,:)
    integer, intent(in) :: width_a, height_a, width_b
    integer, intent(out) :: c(:,:)
    integer :: row_a, col_b, acc, k
    !$omp target teams &
    !$omp&       distribute parallel do collapse(2) &
    !$omp&       !nowait depend(in: a, b) depend(out: c)
    do row_a = 1, size(a, 2)
      do col_b = 1, size(b, 1)
        acc = 0
        do k = 1, size(a, 1)
          acc = acc + a(k, row_a) * b(col_b, k)
        end do
        c(col_b, row_a) = acc
      end do
    end do
    !$omp end target teams distribute parallel do
  end subroutine

  ! OpenCL-style tiled version
  subroutine mat_mul_cl(a, b, c, width_a, height_a, width_b)
    integer, intent(in) :: a(:,:), b(:,:)
    integer, intent(in) :: width_a, height_a, width_b
    integer, intent(out) :: c(:,:)
    integer :: block_a(0:TILE_SIZE-1, 0:TILE_SIZE-1)
    integer :: block_b(0:TILE_SIZE-1, 0:TILE_SIZE-1)
    integer row_a_base, col_b_base, k_base, x, y, k
    !$omp target teams &
    !$omp&       distribute collapse(2) &
    !$omp&       thread_limit(TILE_SIZE*TILE_SIZE) &
    !$omp&       private(block_a, block_b) &
    !$omp&       !nowait depend(in: a, b) depend(out: c)
    do row_a_base = 1, size(a, 2), TILE_SIZE
      do col_b_base = 1, size(b, 1), TILE_SIZE
        !$omp parallel num_threads(TILE_SIZE*TILE_SIZE) &
        !$omp&         private(x, y, acc)
        x = mod(omp_get_thread_num(), TILE_SIZE);
        y = omp_get_thread_num() / TILE_SIZE;

        acc = 0
        do k_base = 1, size(a, 1), TILE_SIZE
          ! Load tiles
          block_a(x, y) = a(k_base+x, row_a_base+y)
          block_b(x, y) = b(col_b_base+x, k_base+y)
          !$omp barrier

          ! Tile multiplication
          do k = 0, TILE_SIZE-1
            acc = acc + block_a(k, y) * block_b(x, k)
          end do
          !$omp barrier
        end do

        ! Store result
        c(col_b_base+x, row_a_base+y) = acc
        !$omp end parallel
      end do
    end do
    !$omp end target teams distribute
  end subroutine

end module

program mat_mul_benchmark
  use omp_lib
  use mat_mul_kernels

  implicit none

  ! Parameters
  integer, parameter :: width_a = 1024
  integer, parameter :: height_a = 1024
  integer, parameter :: width_b = 1024
  integer, parameter :: num_warmup_runs = 5
  integer, parameter :: num_runs = 25

  ! Locals
  integer :: x, y, i, acc, variant
  real :: start, fin, duration_us, r
  logical :: ok
  character(len=16) :: success, variant_str

  ! Matrices
  integer, dimension(:,:), allocatable :: a, b, c
  allocate(a(width_a, height_a))
  allocate(b(width_b, width_a))
  allocate(c(width_b, height_a))

  ! GPU-side buffers
  !$omp target enter data map(alloc:a, b, c)

  do variant = 1, 2

    ! Initialise
    do y = 1, height_a
      do x = 1, width_a
        call random_number(r)
        a(x, y) = int(r*100.0)
      end do
    end do

    do y = 1, width_a
      do x = 1, width_b
        call random_number(r)
        b(x, y) = int(r*100.0)
      end do
    end do

    c(:,:) = 0

    ! Copy data to device
    !$omp target update to(a, b, c)

    do i = 1, num_warmup_runs
      if (variant == 1) then
        call mat_mul_simple(a, b, c, width_a, height_a, width_b)
      else
        call mat_mul_cl(a, b, c, width_a, height_a, width_b)
      end if
    end do
    !$omp taskwait

    call cpu_time(start);
    do i = 1, num_runs
      if (variant == 1) then
        call mat_mul_simple(a, b, c, width_a, height_a, width_b)
      else
        call mat_mul_cl(a, b, c, width_a, height_a, width_b)
      end if
    end do
    !$omp taskwait
    call cpu_time(fin);

    ! Copy data from device
    !$omp target update from(c)

    ! Check output
    ok = .true.
    do y = 1, height_a
      do x = 1, width_b
        acc = 0
        do i = 1, width_a
          acc = acc + a(i, y) * b(x, i)
        end do
        ok = ok .and. c(x, y) == acc
      end do
    end do

    duration_us = (fin-start) / real(num_runs)

    if (ok) then
      success = "PASS"
    else
      success = "FAIL"
    end if

    if (variant == 1) then
      variant_str = "simple"
    else
      variant_str = "cl"
    end if

    write (*,'(A,A,A,A,A,F0.6)') &
      'RESULT,OpenMP/Fortran,mat_mul/', &
      trim(variant_str), ',', &
      trim(success), ',', &
      1000.0*duration_us

  end do

end program
