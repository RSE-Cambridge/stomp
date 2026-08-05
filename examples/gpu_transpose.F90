! Tile size for optimised version
#define TILE_SIZE 32

module transpose_kernels
  use omp_lib

contains

  ! Simple untiled version
  subroutine trans_simple(mat_in, mat_out)
    integer, intent(in) :: mat_in(:,:)
    integer, intent(out) :: mat_out(:,:)
    integer :: x, y
    !$omp target teams &
    !$omp&       distribute parallel do collapse(2) &
    !$omp&       !nowait depend(in: mat_in) depend(out: mat_out)
    do y = 1, size(mat_in, 2)
      do x = 1, size(mat_in, 1)
        mat_out(y, x) = mat_in(x, y)
      end do
    end do
    !$omp end target teams distribute parallel do
  end subroutine

  ! OpenCL-style tiled version
  subroutine trans_cl(mat_in, mat_out)
    integer, intent(in) :: mat_in(:,:)
    integer, intent(out) :: mat_out(:,:)
    integer :: blk(0:TILE_SIZE, 0:TILE_SIZE-1)
    integer :: originX, originY, x, y
    !$omp target teams &
    !$omp&       distribute collapse(2) &
    !$omp&       thread_limit(TILE_SIZE) &
    !$omp&       private(blk) &
    !$omp&       !nowait depend(in: mat_in) depend(out: mat_out)
    do originY = 1, size(mat_in, 2), TILE_SIZE
      do originX = 1, size(mat_in, 1), TILE_SIZE
        !$omp parallel num_threads(TILE_SIZE) private(x)
        x = omp_get_thread_num()

        do y = 0, TILE_SIZE-1
          blk(x, y) = mat_in(originX+x, originY+y)
        end do

        !$omp barrier

        do y = 0, TILE_SIZE-1
          mat_out(originY+x, originX+y) = blk(y, x)
        end do
        !$omp end parallel
      end do
    end do
    !$omp end target teams distribute
  end subroutine

end module

program transpose_benchmark
  use omp_lib
  use transpose_kernels

  implicit none

  ! Parameters
  integer, parameter :: width = 4096
  integer, parameter :: height = 4096
  integer, parameter :: num_warmup_runs = 5
  integer, parameter :: num_runs = 25

  ! Locals
  integer :: x, y, i, variant
  real :: start, fin, duration_us, r
  logical :: ok
  character(len=16) :: success, variant_str

  ! Matrices
  integer, dimension(:,:), allocatable :: m_in, m_out
  allocate(m_in(width, height))
  allocate(m_out(height, width))

  ! GPU-side buffers
  !$omp target enter data map(alloc:m_in, m_out)

  do variant = 1, 2

    ! Initialise
    do y = 1, height
      do x = 1, width
        call random_number(r)
        m_in(x, y) = int(r*100.0)
        m_out(x, y) = 0
      end do
    end do

    ! Copy data to device
    !$omp target update to(m_in, m_out)

    do i = 1, num_warmup_runs
      if (variant == 1) then
        call trans_simple(m_in, m_out)
      else
        call trans_cl(m_in, m_out)
      end if
    end do
    !$omp taskwait

    call cpu_time(start);
    do i = 1, num_runs
      if (variant == 1) then
        call trans_simple(m_in, m_out)
      else
        call trans_cl(m_in, m_out)
      end if
    end do
    !$omp taskwait
    call cpu_time(fin);

    ! Copy data from device
    !$omp target update from(m_out)

    ! Check output
    ok = .true.
    do y = 1, height
      do x = 1, width
        ok = ok .and. m_out(y, x) == m_in(x, y)
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
      'RESULT,OpenMP/Fortran,transpose/', &
      trim(variant_str), ',', &
      trim(success), ',', &
      1000.0*duration_us

  end do

end program
