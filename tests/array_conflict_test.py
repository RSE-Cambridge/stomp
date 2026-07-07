from stomp.test_helpers import stomp_test, Msg


def test_reverse_ok():
    code = '''
subroutine reverse(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, n, tmp
  n = size(arr)
  !$omp parallel do private(tmp)
  do i = 1, n/2
    tmp = arr(i)
    arr(i) = arr(n+1-i)
    arr(n+1-i) = tmp
  end do
end subroutine
'''
    stomp_test(code, [])


def test_reverse_bad():
    code = '''
subroutine reverse(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, n, tmp
  n = size(arr)
  !$omp parallel do private(tmp)
  do i = 1, n
    tmp = arr(i)
    arr(i) = arr(n+1-i)
    arr(n+1-i) = tmp
  end do
end subroutine
'''
    stomp_test(code, [Msg.ParallelArrayConflict])


def test_simd_reverse_ok():
    code = '''
subroutine reverse(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, n, tmp
  n = size(arr)
  !$omp simd private(tmp)
  do i = 1, n/2
    tmp = arr(i)
    arr(i) = arr(n+1-i)
    arr(n+1-i) = tmp
  end do
end subroutine
'''
    stomp_test(code, [])


def test_simd_reverse_bad():
    code = '''
subroutine reverse(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, n, tmp
  n = size(arr)
  !$omp simd private(tmp)
  do i = 1, n
    tmp = arr(i)
    arr(i) = arr(n+1-i)
    arr(n+1-i) = tmp
  end do
end subroutine
'''
    stomp_test(code, [Msg.ParallelArrayConflict])


def test_transpose_untiled_ok():
    code = '''
subroutine trans_simple(mat_in, mat_out)
  integer, intent(in) :: mat_in(:,:)
  integer, intent(out) :: mat_out(:,:)
  integer :: x, y
  !$omp target teams &
  !$omp&       distribute parallel do collapse(2)
  do y = 1, size(mat_in, 2)
    do x = 1, size(mat_in, 1)
      mat_out(y, x) = mat_in(x, y)
    end do
  end do
  !$omp end target teams distribute parallel do
end subroutine
'''
    stomp_test(code, [])


def test_transpose_untiled_bad():
    code = '''
subroutine trans_simple(mat)
  integer, intent(inout) :: mat(:,:)
  integer :: x, y
  !$omp target teams &
  !$omp&       distribute parallel do collapse(2)
  do y = 1, size(mat, 2)
    do x = 1, size(mat, 1)
      mat(y, x) = mat(x, y)
    end do
  end do
  !$omp end target teams distribute parallel do
end subroutine
'''
    stomp_test(code, [Msg.ParallelArrayConflict])


def test_transpose_tiled_ok():
    code = '''
subroutine trans_cl(mat_in, mat_out, tile_size)
  integer, intent(in) :: mat_in(:,:), tile_size
  integer, intent(out) :: mat_out(:,:)
  integer :: blk(0:tile_size, 0:tile_size-1)
  integer :: originX, originY, x, y

  !$omp target teams &
  !$omp&       distribute collapse(2) &
  !$omp&       private(blk)
  do originY = 1, size(mat_in, 2), tile_size
    do originX = 1, size(mat_in, 1), tile_size
      !$omp parallel num_threads(tile_size) private(x)
      x = omp_get_thread_num()

      do y = 0, tile_size-1
        blk(x, y) = mat_in(originX+x, originY+y)
      end do

      !$omp barrier

      do y = 0, tile_size-1
        mat_out(originY+x, originX+y) = blk(y, x)
      end do
      !$omp end parallel
    end do
  end do
  !$omp end target teams distribute
end subroutine
'''
    stomp_test(code, [])


def test_transpose_tiled_bad():
    code = '''
subroutine trans_cl(mat_in, mat_out, tile_size)
  integer, intent(in) :: mat_in(:,:), tile_size
  integer, intent(out) :: mat_out(:,:)
  integer :: blk(0:tile_size, 0:tile_size-1)
  integer :: originX, originY, x, y

  !$omp target teams &
  !$omp&       distribute collapse(2) &
  !$omp&       private(blk)
  do originY = 1, size(mat_in, 2), tile_size
    do originX = 1, size(mat_in, 1), tile_size
      !$omp parallel num_threads(tile_size) private(x)
      x = omp_get_thread_num()

      do y = 0, tile_size-1
        blk(x, y) = mat_in(originX+x, originY+y)
      end do

      ! Missing barrier
      ! !$omp barrier

      do y = 0, tile_size-1
        mat_out(originY+x, originX+y) = blk(y, x)
      end do
      !$omp end parallel
    end do
  end do
  !$omp end target teams distribute
end subroutine
'''
    stomp_test(code, [Msg.ParallelArrayConflict])


def test_mat_mul_untiled_ok():
    code = '''
subroutine mat_mul_simple(a, b, c, width_a, height_a, width_b)
  integer, intent(in) :: a(:,:), b(:,:)
  integer, intent(in) :: width_a, height_a, width_b
  integer, intent(out) :: c(:,:)
  integer :: row_a, col_b, acc, k
  !$omp target teams &
  !$omp&       distribute parallel do collapse(2) private(acc)
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
'''
    stomp_test(code, [])


def test_mat_mul_tiled_ok():
    code = '''
subroutine mat_mul_cl(a, b, c, width_a, height_a, width_b, tile_size)
  integer, intent(in) :: a(:,:), b(:,:), tile_size
  integer, intent(in) :: width_a, height_a, width_b
  integer, intent(out) :: c(:,:)
  integer :: block_a(0:tile_size-1, 0:tile_size-1)
  integer :: block_b(0:tile_size-1, 0:tile_size-1)
  integer row_a_base, col_b_base, k_base, x, y, k
  !$omp target teams &
  !$omp&       distribute collapse(2) &
  !$omp&       thread_limit(tile_size*tile_size) &
  !$omp&       private(block_a, block_b)
  do row_a_base = 1, size(a, 2), tile_size
    do col_b_base = 1, size(b, 1), tile_size
      !$omp parallel num_threads(tile_size*tile_size) &
      !$omp&         private(x, y, acc)
      x = mod(omp_get_thread_num(), tile_size);
      y = omp_get_thread_num() / tile_size;

      acc = 0
      do k_base = 1, size(a, 1), tile_size
        ! Load tiles
        block_a(x, y) = a(k_base+x, row_a_base+y)
        block_b(x, y) = b(col_b_base+x, k_base+y)
        !$omp barrier

        ! Tile multiplication
        do k = 0, tile_size-1
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
'''
    stomp_test(code, [])


def test_mat_mul_tiled_bad():
    code = '''
subroutine mat_mul_cl(a, b, c, width_a, height_a, width_b, tile_size)
  integer, intent(in) :: a(:,:), b(:,:), tile_size
  integer, intent(in) :: width_a, height_a, width_b
  integer, intent(out) :: c(:,:)
  integer :: block_a(0:tile_size-1, 0:tile_size-1)
  integer :: block_b(0:tile_size-1, 0:tile_size-1)
  integer row_a_base, col_b_base, k_base, x, y, k
  !$omp target teams &
  !$omp&       distribute collapse(2) &
  !$omp&       thread_limit(tile_size*tile_size) &
  !$omp&       private(block_a, block_b)
  do row_a_base = 1, size(a, 2), tile_size
    do col_b_base = 1, size(b, 1), tile_size
      !$omp parallel num_threads(tile_size*tile_size) &
      !$omp&         private(x, y, acc)
      x = mod(omp_get_thread_num(), tile_size);
      y = omp_get_thread_num() / tile_size;

      acc = 0
      do k_base = 1, size(a, 1), tile_size
        ! Load tiles
        block_a(x, y) = a(k_base+x, row_a_base+y)
        block_b(x, y) = b(col_b_base+x, k_base+y)
        !$omp barrier

        ! Tile multiplication
        do k = 0, tile_size-1
          acc = acc + block_a(k, y) * block_b(x, k)
        end do
        ! Missing barrier
        ! !$omp barrier
      end do

      ! Store result
      c(col_b_base+x, row_a_base+y) = acc
      !$omp end parallel
    end do
  end do
  !$omp end target teams distribute
end subroutine
'''
    stomp_test(code, [Msg.ParallelArrayConflict])


def test_stencil_ok():
    code = '''
subroutine stencil_cl(mat_in, mat_out, tile_size)
  integer, intent(in) :: mat_in(:,:), tile_size
  integer, intent(out) :: mat_out(:,:)
  integer :: blk(0:tile_size-1, 0:tile_size-1)
  integer :: originX, originY, x, y, total
  !$omp target teams &
  !$omp&       distribute collapse(2) &
  !$omp&       thread_limit(tile_size) &
  !$omp&       private(blk)
  do originY = 1, size(mat_in, 2), tile_size-2
    do originX = 1, size(mat_in, 1), tile_size-2
      !$omp parallel num_threads(tile_size) private(x, total)
      x = omp_get_thread_num()

      do y = 0, tile_size-1
        blk(x, y) = mat_in(originX+x, originY+y)
      end do

      !$omp barrier

      if (x > 0 .and. x < tile_size-1) then
        do y = 1, tile_size-2
          total =        blk(x, y-1) +              &
            blk(x-1,y) + blk(x, y  ) + blk(x+1, y)  &
                       + blk(x, y+1)
          mat_out(originX+x, originY+y) = total/5
        end do
      end if
      !$omp end parallel
    end do
  end do
  !$omp end target teams distribute
end subroutine
'''
    stomp_test(code, [])


def test_stencil_bad():
    code = '''
subroutine stencil_cl(mat_in, mat_out, tile_size)
  integer, intent(in) :: mat_in(:,:), tile_size
  integer, intent(out) :: mat_out(:,:)
  integer :: blk(0:tile_size-1, 0:tile_size-1)
  integer :: originX, originY, x, y, total
  !$omp target teams &
  !$omp&       distribute collapse(2) &
  !$omp&       thread_limit(tile_size) &
  !$omp&       private(blk)
  do originY = 1, size(mat_in, 2), tile_size-2
    do originX = 1, size(mat_in, 1), tile_size-2
      !$omp parallel num_threads(tile_size) private(x, total)
      x = omp_get_thread_num()

      do y = 0, tile_size-1
        blk(x, y) = mat_in(originX+x, originY+y)
      end do

      !$omp barrier

      if (x > 0 .and. x < tile_size-1) then
        ! Wrong loop bounds
        do y = 1, tile_size-1
          total =        blk(x, y-1) +              &
            blk(x-1,y) + blk(x, y  ) + blk(x+1, y)  &
                       + blk(x, y+1)
          mat_out(originX+x, originY+y) = total/5
        end do
      end if
      !$omp end parallel
    end do
  end do
  !$omp end target teams distribute
end subroutine
'''
    stomp_test(code, [Msg.ParallelArrayConflict])


def test_consistent_scheduling_static():
    '''Test that loops with the same iteration space have a consistent
    mapping from loop iterations to threads when using static scheduling.'''
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr
  !$omp parallel

  !$omp do schedule(static)
  do i = 1, size(arr)
    arr(i) = 0
  enddo
  !$omp end do nowait

  !$omp do schedule(static)
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do

  !$omp end parallel
end subroutine
'''
    stomp_test(code, [])


def test_consistent_scheduling_default():
    '''Test that loops with the same iteration space do not require a
    consistent mapping from loop iterations to threads when not using
    static scheduling.'''
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr
  !$omp parallel

  !$omp do
  do i = 1, size(arr)
    arr(i) = 0
  enddo
  !$omp end do nowait

  !$omp do
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do

  !$omp end parallel
end subroutine
'''
    stomp_test(code, [Msg.ParallelArrayConflict])


def test_nowait_do_path_to_self():
    '''Test that a nowait do loop with non-static scheduling and a
    barrier-free path back to itself permits different threads to map to
    the same iteration variable.'''
    code = '''
subroutine main()
  integer :: arr(10)
  integer :: nwbins, klev, kbdim, jw, jk

  !$omp parallel private(jk, jw) shared(arr)
  do jw=2,nwbins
    !$omp do
    do jk=1, klev
      arr(jk) = arr(jk) + 1
    end do
    !$omp end do nowait
  end do
  !$omp end parallel
end subroutine
'''
    stomp_test(code, [Msg.ParallelArrayConflict])
