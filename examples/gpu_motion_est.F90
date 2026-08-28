! Search radius in pixels
#define RADIUS 4

! Size of region handled by each workgroup
#define REGION_WIDTH 32
#define REGION_HEIGHT 32

! Threads per region for OpenCL-style version
#define THREADS_PER_REGION 256

module motion_est_kernels
  use omp_lib
  implicit none

contains

  ! Simple version
  subroutine motion_est_simple(curr_frame, prev_frame, sads, &
               regions_wide, regions_high)
    integer, intent(in) :: curr_frame(0:,0:)
    integer, intent(in) :: prev_frame(0:,0:)
    integer, intent(in) :: regions_wide, regions_high
    integer, intent(out) :: sads(0:)
    integer :: outputs_per_region, ry, rx, sad_base, cy, cx, py, px, &
               diff, x, y, ncy, ncx, npy, npx, out_count, sad, pyo, pxo, &
               width, height

    width = regions_wide * REGION_WIDTH
    height = regions_high * REGION_HEIGHT
    outputs_per_region = &
      (REGION_WIDTH/4) * (REGION_HEIGHT/4) * (2*RADIUS+1) * (2*RADIUS+1)

    !$omp target teams distribute collapse(2) &
    !$omp&       private(sad_base) &
    !$omp&       !nowait depend(in: curr_frame, prev_frame) depend(out: sads)
    do ry = 0, regions_high-1
      do rx = 0, regions_wide-1
        sad_base = (ry*regions_wide+rx)*outputs_per_region
        !$omp parallel do collapse(4) &
        !$omp&  private(sad, diff, ncy, ncx, npy, npx, out_count, py, px)
        do cy = ry*REGION_HEIGHT, (ry+1)*REGION_HEIGHT - 1, 4
          do cx = rx*REGION_WIDTH, (rx+1)*REGION_WIDTH - 1, 4
            do pyo = -RADIUS, RADIUS
              do pxo = -RADIUS, RADIUS
                py = cy+pyo
                px = cx+pxo
                sad = 0
                do y = 0, 3
                  do x = 0, 3
                    diff = curr_frame(cx+x, cy+y)
                    if (py + y >= 0 .and. py + y < height .and. &
                        px + x >= 0 .and. px + x < width) then
                      diff = diff - prev_frame(px+x, py+y)
                    end if
                    if (diff < 0) then
                      diff = -diff
                    end if
                    sad = sad + diff
                  end do
                end do
                ! Determine output location
                ncy = (cy-ry*REGION_HEIGHT)/4
                ncx = (cx-rx*REGION_HEIGHT)/4
                npy = py-(cy-RADIUS)
                npx = px-(cx-RADIUS)
                out_count = &
                  ncy * (REGION_WIDTH/4) * (2*RADIUS+1) * (2*RADIUS+1) + &
                  ncx * (2*RADIUS+1) * (2*RADIUS+1) + &
                  npy * (2*RADIUS+1) +  &
                  npx
                sads(sad_base+out_count) = sad
              end do
            end do
          end do
        end do
      end do
    end do
  end subroutine

  ! OpenCL-style version
  subroutine motion_est_cl(curr_frame, prev_frame, sads, regions_wide, regions_high)
    integer, intent(in) :: curr_frame(0:,0:)
    integer, intent(in) :: prev_frame(0:,0:)
    integer, intent(in) :: regions_wide, regions_high
    integer, intent(out) :: sads(0:)
    integer :: gy, gx, origin_x, origin_y, y, x, frame_x, frame_y, &
               x_blocks, y_blocks, num_blocks, i, &
               outputs_per_block, num_outputs, sad_base, &
               block_id, vec_id, block_id_x, block_id_y, curr_x, curr_y, &
               vec_id_x, vec_id_y, prev_x, prev_y, sad, diff, &
               width, height
    integer :: curr_region(0:REGION_WIDTH-1, 0:REGION_HEIGHT-1)
    integer :: prev_region(0:REGION_WIDTH+2*RADIUS-1, &
                           0:REGION_HEIGHT+2*RADIUS-1)

    width = regions_wide * REGION_WIDTH
    height = regions_high * REGION_HEIGHT

    !$omp target teams distribute collapse(2) &
    !$omp&       thread_limit(THREADS_PER_REGION) &
    !$omp&       private(curr_region, prev_region, origin_x, origin_y) &
    !$omp&       !nowait depend(in: curr_frame, prev_frame) depend(out: sads)
    do gy = 0, regions_high - 1
      do gx = 0, regions_wide - 1
        origin_x = gx * REGION_WIDTH
        origin_y = gy * REGION_HEIGHT

        !$omp parallel num_threads(THREADS_PER_REGION) &
        !$omp& private(frame_x, frame_y, x_blocks, y_blocks, num_blocks, &
        !$omp&         outputs_per_block, num_outputs, sad_base, &
        !$omp&         block_id, vec_id, block_id_x, block_id_y, curr_x, &
        !$omp&         curr_y, vec_id_x, vec_id_y, prev_x, prev_y, sad, diff)
          ! Load current frame's region
          do y = 0, REGION_HEIGHT-1
            do x = omp_get_thread_num(), REGION_WIDTH-1, THREADS_PER_REGION
              frame_x = origin_x+x
              frame_y = origin_y+y
              curr_region(x, y) = curr_frame(frame_x, frame_y)
            end do
          end do

          ! Load previous frame's region
          do y = 0, REGION_HEIGHT + 2*RADIUS - 1
            do x = omp_get_thread_num(), REGION_WIDTH + 2*RADIUS - 1, &
                                         THREADS_PER_REGION
              frame_x = origin_x+x-RADIUS
              frame_y = origin_y+y-RADIUS
              if (frame_x < 0 .or. frame_x >= width .or. &
                  frame_y < 0 .or. frame_y >= height) then
                prev_region(x, y) = 0
              else
                prev_region(x, y) = prev_frame(frame_x, frame_y)
              end if
            end do
          end do

          !$omp barrier

          ! Compute all SADs
          x_blocks = REGION_WIDTH/4
          y_blocks = REGION_HEIGHT/4
          num_blocks = x_blocks*y_blocks
          outputs_per_block = (2*RADIUS+1) * (2*RADIUS+1)
          num_outputs = num_blocks * outputs_per_block
          sad_base = (gy * regions_wide + gx) * num_outputs
          do i = omp_get_thread_num(), num_outputs-1, THREADS_PER_REGION
            ! Which block in current frame are we processing?
            block_id = i / outputs_per_block
            ! Which motion vector are we computing?
            vec_id = i - block_id*outputs_per_block

            ! Origin of current block
            block_id_x = mod(block_id, x_blocks)
            block_id_y = block_id / x_blocks
            curr_x = block_id_x * 4
            curr_y = block_id_y * 4

            ! Origin of previous block
            vec_id_x = mod(vec_id, 2*RADIUS+1)
            vec_id_y = vec_id / (2*RADIUS+1)
            prev_x = curr_x + vec_id_x
            prev_y = curr_y + vec_id_y

            ! Compute SAD for current motion vector
            sad = 0
            do y = 0, 3
              do x = 0, 3
                diff = curr_region(curr_x+x, curr_y+y) - &
                       prev_region(prev_x+x, prev_y+y)
                if (diff < 0) then
                  diff = -diff
                end if
                sad = sad + diff
              end do
            end do
            sads(sad_base+i) = sad
          end do
        !$omp end parallel
      end do
    end do
  end subroutine

end module

program motion_est_benchmark
  use omp_lib
  use motion_est_kernels
  implicit none

  ! Parameters
  integer, parameter :: threads_per_region = 256
  integer, parameter :: regions_wide = 80
  integer, parameter :: width = REGION_WIDTH * regions_wide
  integer, parameter :: regions_high = 80
  integer, parameter :: height = REGION_HEIGHT * regions_high
  integer, parameter :: num_warmup_runs = 5
  integer, parameter :: num_runs = 25

  ! Locals
  integer :: x, y, i, variant, outputs_per_region, total_outputs, &
             rx, ry, cx, cy, px, py, out_count, sad_base, diff, sad
  real :: start, fin, duration_us, r
  logical :: ok
  character(len=16) :: success, variant_str

  ! Kernel arguments
  integer, dimension(:,:), allocatable :: curr_frame, prev_frame
  integer, dimension(:), allocatable :: sads

  outputs_per_region = &
    (REGION_WIDTH/4) * (REGION_HEIGHT/4) * (2*RADIUS+1) * (2*RADIUS+1)
  total_outputs = &
    outputs_per_region * (width/REGION_WIDTH) * (height/REGION_HEIGHT)

  ! Allocate buffers
  allocate(curr_frame(0:width-1, 0:height-1))
  allocate(prev_frame(0:width-1, 0:height-1))
  allocate(sads(0:total_outputs-1))

  ! GPU-side buffers
  !$omp target enter data map(alloc:curr_frame, prev_frame, sads)

  do variant = 1, 2

    ! Initialise
    do y = 0, height-1
      do x = 0, width-1
        call random_number(r)
        curr_frame(x, y) = int(r*100.0)
        call random_number(r)
        prev_frame(x, y) = int(r*100.0)
      end do
    end do

    ! Copy data to device
    !$omp target update to(curr_frame, prev_frame)

    do i = 1, num_warmup_runs
      if (variant == 1) then
        call motion_est_simple(curr_frame, prev_frame, sads, &
               regions_wide, regions_high)
      else
        call motion_est_cl(curr_frame, prev_frame, sads, &
               regions_wide, regions_high)
      end if
    end do
    !$omp taskwait

    call cpu_time(start);
    do i = 1, num_runs
      if (variant == 1) then
        call motion_est_simple(curr_frame, prev_frame, sads, &
               regions_wide, regions_high)
      else
        call motion_est_cl(curr_frame, prev_frame, sads, &
               regions_wide, regions_high)
      end if
    end do
    !$omp taskwait
    call cpu_time(fin);

    ! Copy data from device
    !$omp target update from(sads)

    ! Check output
    ok = .true.
    do ry = 0, (height/REGION_HEIGHT)-1
      do rx = 0, (width/REGION_WIDTH)-1
        out_count = 0
        sad_base = (ry*(width/REGION_WIDTH)+rx)*outputs_per_region
        do cy = ry*REGION_HEIGHT, (ry+1)*REGION_HEIGHT - 1, 4
          do cx = rx*REGION_WIDTH, (rx+1)*REGION_WIDTH - 1, 4
            do py = cy-RADIUS, cy+RADIUS
              do px = cx-RADIUS, cx+RADIUS
                sad = 0
                do y = 0, 3
                  do x = 0, 3
                    diff = curr_frame(cx+x, cy+y)
                    if (py + y >= 0 .and. py + y < height .and. &
                        px + x >= 0 .and. px + x < width) then
                      diff = diff - prev_frame(px+x, py+y)
                    end if
                    if (diff < 0) then
                      diff = -diff
                    end if
                    sad = sad + diff
                  end do
                end do
                ok = ok .and. sads(sad_base+out_count) == sad
                out_count = out_count+1
              end do
            end do
          end do
        end do
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
      'RESULT,OpenMP/Fortran,motion_est/', &
      trim(variant_str), ',', &
      trim(success), ',', &
      1000.0*duration_us

  end do

end program
