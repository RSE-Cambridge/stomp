#define THREADS_PER_GROUP 256

module histo_kernels
  use omp_lib
  use iso_fortran_env

contains

  ! Simple version
  subroutine histo_simple(arr, n, num_groups, output)
    integer(kind=int8), intent(in) :: arr(0:)
    integer, intent(in) :: n
    integer, intent(in) :: num_groups
    integer, intent(out) :: output(0:)
    integer :: g, elems_per_group
    integer :: bins(-128:127)
    elems_per_group = n / num_groups
    !$omp target teams distribute &
    !$omp&       private(bins) &
    !$omp&       !nowait depend(in: arr) depend(out: output)
    do g = 0, num_groups-1
      !$omp parallel do
      do i = -128, 127
        bins(i) = 0
      end do
      !$omp end parallel do

      !$omp parallel do
      do i = 0, elems_per_group-1
        !$omp atomic
        bins(arr(g*elems_per_group+i)) = bins(arr(g*elems_per_group+i)) + 1
        !$omp end atomic
      end do
      !$omp end parallel do

      !$omp parallel do
      do i = -128, 127
        output(g*256+128+i) = bins(i)
      end do
      !$omp end parallel do
    end do
    !$omp end target teams distribute
  end subroutine

  ! OpenCL-style version
  subroutine histo_cl(arr, n, num_groups, output)
    integer(kind=int8), intent(in) :: arr(0:)
    integer, intent(in) :: n
    integer, intent(in) :: num_groups
    integer, intent(out) :: output(0:)
    integer :: g, elems_per_group, t
    integer :: bins(-128:127)
    integer(kind=int8) :: byte
    elems_per_group = n / num_groups

    !$omp target teams distribute &
    !$omp&       private(bins) &
    !$omp&       thread_limit(THREADS_PER_GROUP) &
    !$omp&       !nowait depend(in: arr) depend(out: output)
    do g = 0, num_groups-1
      !$omp parallel num_threads(THREADS_PER_GROUP) private(t, byte)
        t = omp_get_thread_num()

        do i = t-128, 127, THREADS_PER_GROUP
          bins(i) = 0
        end do
        !$omp barrier
        do i = t, elems_per_group-1, THREADS_PER_GROUP
          byte = arr(g*elems_per_group+i)
          !$omp atomic
          bins(byte) = bins(byte) + 1
          !$omp end atomic
        end do
        !$omp barrier
        do i = t-128, 127, THREADS_PER_GROUP
          output(g*256+128+i) = bins(i)
        end do
      !$omp end parallel
    end do
    !$omp end target teams distribute
  end subroutine
end module

program histo_benchmark
  use omp_lib
  use iso_fortran_env
  use histo_kernels

  implicit none

  ! Parameters
  integer, parameter :: n = 33554432
  integer, parameter :: num_groups = 2048
  integer, parameter :: num_warmup_runs = 5
  integer, parameter :: num_runs = 25

  ! Locals
  integer :: i, variant, g, elems_per_group
  integer :: golden_bins(-128:127)
  integer(kind=int8) :: byte
  real :: start, fin, duration_us, r
  logical :: ok
  character(len=16) :: success, variant_str

  ! Kernel parameters
  integer(kind=int8), allocatable :: arr(:)
  integer, allocatable :: output(:)

  allocate(arr(0:n-1))
  allocate(output(0:256*num_groups-1))
  elems_per_group = n / num_groups

  ! GPU-side buffers
  !$omp target enter data map(alloc:arr, output)

  do variant = 1, 2

    ! Initialise
    do i = 0, n-1
      call random_number(r)
      arr(i) = int(r*255.0) - 128
    end do

    ! Copy data to device
    !$omp target update to(arr, output)

    do i = 1, num_warmup_runs
      if (variant == 1) then
        call histo_simple(arr, n, num_groups, output)
      else
        call histo_cl(arr, n, num_groups, output)
      end if
    end do
    !$omp taskwait

    call cpu_time(start);
    do i = 1, num_runs
      if (variant == 1) then
        call histo_simple(arr, n, num_groups, output)
      else
        call histo_cl(arr, n, num_groups, output)
      end if
    end do
    !$omp taskwait
    call cpu_time(fin);

    ! Copy data from device
    !$omp target update from(output)

    ! Check output
    ok = .true.
    do g = 0, num_groups-1
      do i = -128, 127
        golden_bins(i) = 0
      end do
      do i = 0, elems_per_group-1
        byte = arr(g*elems_per_group+i)
        golden_bins(byte) = golden_bins(byte) + 1
      end do
      do i = -128, 127
        ok = ok .and. output(g*256+i+128) == golden_bins(i)
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
      'RESULT,OpenMP/Fortran,histogram/', &
      trim(variant_str), ',', &
      trim(success), ',', &
      1000.0*duration_us

  end do

end program
