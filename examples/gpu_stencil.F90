! Tile size for optimised version
#define TILE_SIZE 32

module stencil_kernels
  use omp_lib

contains

  ! Simple untiled version
  subroutine stencil_simple(mat_in, mat_out)
    integer, intent(in) :: mat_in(:,:)
    integer, intent(out) :: mat_out(:,:)
    integer :: x, y, total
    !$omp target teams &
    !$omp&       distribute parallel do collapse(2) &
    !$omp&       !nowait depend(in: mat_in) depend(out: mat_out)
    do y = 2, size(mat_in, 2)-1
      do x = 2, size(mat_in, 1)-1
        total =          mat_in(x, y-1) +                 &
         mat_in(x-1,y) + mat_in(x, y  ) + mat_in(x+1, y)  &
                       + mat_in(x, y+1)
        mat_out(x, y) = total/4;
      end do
    end do
    !$omp end target teams distribute parallel do
  end subroutine

  ! OpenCL-style tiled version
  subroutine stencil_cl(mat_in, mat_out)
    integer, intent(in) :: mat_in(:,:)
    integer, intent(out) :: mat_out(:,:)
    integer :: blk(0:TILE_SIZE-1, 0:TILE_SIZE-1)
    integer :: originX, originY, x, y, total
    !$omp target teams &
    !$omp&       distribute collapse(2) &
    !$omp&       thread_limit(TILE_SIZE) &
    !$omp&       private(blk) &
    !$omp&       !nowait depend(in: mat_in) depend(out: mat_out)
    do originY = 1, size(mat_in, 2), TILE_SIZE-2
      do originX = 1, size(mat_in, 1), TILE_SIZE-2
        !$omp parallel num_threads(TILE_SIZE) private(x, total)
        x = omp_get_thread_num()

        do y = 0, TILE_SIZE-1
          blk(x, y) = mat_in(originX+x, originY+y)
        end do

        !$omp barrier

        if (x > 0 .and. x < TILE_SIZE-1) then
          do y = 1, TILE_SIZE-2
            total =        blk(x, y-1) +              &
              blk(x-1,y) + blk(x, y  ) + blk(x+1, y)  &
                         + blk(x, y+1)
            mat_out(originX+x, originY+y) = total/4
          end do
        end if
        !$omp end parallel
      end do
    end do
    !$omp end target teams distribute
  end subroutine

end module

program stencil_benchmark
  use omp_lib
  use stencil_kernels

  implicit none

  ! Parameters
  integer, parameter :: width = 4096
  integer, parameter :: height = 4096
  integer, parameter :: num_warmup_runs = 5
  integer, parameter :: num_runs = 25

  ! Locals
  integer :: x, y, i, variant, total, pwidth, pheight, nhigh, nwide
  real :: start, fin, duration_us, r
  logical :: ok
  character(len=16) :: success, variant_str

  ! Matrices
  integer, dimension(:,:), allocatable :: m_in, m_out

  ! Pad the array so that width and height are multiples of (TILE_SIZE-2)
  nwide = (width+TILE_SIZE-1) / (TILE_SIZE-2)
  pwidth = nwide * (TILE_SIZE-2)  ! Padded width
  nhigh = (width+TILE_SIZE-1) / (TILE_SIZE-2)
  pheight = nhigh * (TILE_SIZE-2)  ! Padded height

  allocate(m_in(pwidth, pheight))
  allocate(m_out(pwidth, pheight))

  ! GPU-side buffers
  !$omp target enter data map(alloc:m_in, m_out)

  do variant = 1, 2

    ! Initialise
    do y = 1, pheight
      do x = 1, pwidth
        call random_number(r)
        m_in(x, y) = int(r*100.0)
        m_out(x, y) = 0
      end do
    end do

    ! Copy data to device
    !$omp target update to(m_in, m_out)

    do i = 1, num_warmup_runs
      if (variant == 1) then
        call stencil_simple(m_in, m_out)
      else
        call stencil_cl(m_in, m_out)
      end if
    end do
    !$omp taskwait

    call cpu_time(start);
    do i = 1, num_runs
      if (variant == 1) then
        call stencil_simple(m_in, m_out)
      else
        call stencil_cl(m_in, m_out)
      end if
    end do
    !$omp taskwait
    call cpu_time(fin);

    ! Copy data from device
    !$omp target update from(m_out)

    ! Check output
    ok = .true.
    do y = 2, height-1
      do x = 2, width-1
        total =         m_in(x, y-1) +               &
          m_in(x-1,y) + m_in(x, y  ) + m_in(x+1, y)  &
                      + m_in(x, y+1)
        ok = ok .and. m_out(x, y) == total/4
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
      'RESULT,OpenMP/Fortran,stencil/', &
      trim(variant_str), ',', &
      trim(success), ',', &
      1000.0*duration_us

  end do

end program
