# SPDX-License-Identifier: BSD-3-Clause

from stomp.test_helpers import stomp_test, Msg


def test_reverse_infer():
    code = '''
subroutine reverse(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, n, tmp
  n = size(arr)
  do i = 1, n/2
    tmp = arr(i)
    arr(i) = arr(n+1-i)
    arr(n+1-i) = tmp
  end do
end subroutine
'''
    stomp_test(code, [Msg.FoundParallelisableLoop], infer=True)


def test_oetranspose_infer():
    code = '''
subroutine odd_even_transposition(arr, start)
  integer , intent(inout) :: arr(:)
  integer, intent(in) :: start
  integer :: i, tmp
  do i = start, size(arr)-1, 2
    if (arr(i) > arr(i+1)) then
      tmp = arr(i+1)
      arr(i+1) = arr(i)
      arr(i) = tmp
    end if
  end do
end subroutine
'''
    stomp_test(code, [Msg.FoundParallelisableLoop], infer=True)


def test_matmul_infer():
    code = '''
subroutine my_matmul(a, b, c, chunk_size)
  integer, intent(in) :: a(:,:), b(:,:)
  integer, intent(out) :: c(:,:)
  integer, intent(in) :: chunk_size
  integer :: x, y, k, k_tile, x_tile, y_tile

  c(:,:) = 0
  do y_tile = 1, size(a, 2), chunk_size
    do x_tile = 1, size(b, 1), chunk_size
      do k_tile = 1, size(a, 1), chunk_size
        do y = y_tile, min(y_tile + (chunk_size - 1), size(a, 2)), 1
          do x = x_tile, min(x_tile + (chunk_size - 1), size(b, 1)), 1
            do k = k_tile, min(k_tile + (chunk_size - 1), size(a, 1)), 1
              c(x,y) = c(x,y) + a(k,y) * b(x,k)
            enddo
          enddo
        enddo
      enddo
    enddo
  enddo
end subroutine my_matmul
'''
    stomp_test(code, [Msg.FoundParallelisableLoop] * 4, infer=True)


def test_chunking_infer():
    code = '''
module chunking_example
contains

  subroutine chunking(arr, chunk_size)
    integer, dimension(:), intent(inout) :: arr
    integer, intent(in) :: chunk_size
    integer :: n, chunk_begin, chunk_end

    n = size(arr)
    do chunk_begin = 1, n, chunk_size
      chunk_end = min(chunk_begin+chunk_size-1, n)
      call modify(arr(chunk_begin:chunk_end))
    end do
  end subroutine

  pure subroutine modify(a)
    integer, intent(inout) :: a(:)
  end subroutine

end module
'''
    stomp_test(code, [Msg.FoundParallelisableLoop], infer=True)


def test_flatten_infer():
    code = '''
subroutine flatten(mat, arr)
  real, intent(in) :: mat(0:,0:)
  real, intent(out) :: arr(0:)
  integer :: x, y
  integer :: nx, ny
  nx = size(mat, 1)
  ny = size(mat, 2)
  do y = 0, ny-1
    do x = 0, nx-1
      arr(nx * y + x) = mat(x, y)
    end do
  end do
end subroutine
'''
    stomp_test(code, [Msg.FoundParallelisableLoop] * 2, infer=True)


def test_gauss_jordan_infer():
    code = '''
! Code from: https://www.numericalmethods.in/pages/sle/02gaussJordan.html
subroutine gauss_jordan(a, n)
  real, intent(inout) :: a(:,:)
  integer, intent(in) :: n
  integer :: i, j, k
  real :: ratio
  do k = 1, n
    do i = 1, n
      if (i /= k) then
        ratio = a(i,k) / a(k,k)
        do j=1,n+1
          a(i,j) = a(i,j) - a(k,j)*ratio
        end do
      end if
    end do
  end do
end subroutine
'''
    stomp_test(code, [Msg.FoundParallelisableLoop] * 2, infer=True)


def test_transpose_infer():
    code = '''
subroutine my_transpose(m_in, m_out, chunk_size)
  real, dimension(:,:), intent(in) :: m_in
  real, dimension(:,:), intent(out) :: m_out
  integer, intent(in) :: chunk_size
  integer :: x, y, x_tile, y_tile

  do y_tile = 1, size(m_in, 2), chunk_size
    do x_tile = 1, size(m_in, 1), chunk_size
      do y = y_tile, min(y_tile + (chunk_size - 1), size(m_in, 2)), 1
        do x = x_tile, min(x_tile + (chunk_size - 1), size(m_in, 1)), 1
          m_out(x,y) = m_in(y,x)
        enddo
      enddo
    enddo
  enddo
end subroutine my_transpose
'''
    stomp_test(code, [Msg.FoundParallelisableLoop] * 4, infer=True)


def test_parallel_prefix_infer():
    code = '''
subroutine parallel_prefix_sum(arr, chunk_size)
  integer, intent(inout) :: arr(0:)
  integer, intent(in) :: chunk_size
  integer :: inc_by(0:chunk_size-1)
  integer :: n, chunk_begin, chunk_end, chunk_id, i, acc

  n = size(arr)
  do chunk_begin = 0, n-1, chunk_size
    chunk_end = min(chunk_begin + chunk_size - 1, n-1)
    acc = 0
    do i = chunk_begin, chunk_end
      acc = acc + arr(i)
      arr(i) = acc
    end do
  end do

  acc = 0
  do chunk_begin = 0, n-1, chunk_size
    chunk_end = min(chunk_begin + chunk_size - 1, n-1)
    chunk_id = chunk_begin / chunk_size
    inc_by(chunk_id) = acc
    acc = acc + arr(chunk_end)
  end do

  do chunk_begin = chunk_size, n-1, chunk_size
    chunk_end = min(chunk_begin + chunk_size - 1, n-1)
    chunk_id = chunk_begin / chunk_size
    do i = chunk_begin, chunk_end
      arr(i) = arr(i) + inc_by(chunk_id)
    end do
  end do
end subroutine
'''
    stomp_test(code, [Msg.FoundParallelisableLoop] * 3, infer=True)


def test_oemsort_infer():
    code = '''
! Based on psuedocode from:
!   https://en.wikipedia.org/wiki/Batcher_odd%E2%80%93even_mergesort
subroutine odd_even_merge_sort(arr, log_n)
  integer, intent(inout) :: arr(0:)
  integer, intent(in) :: log_n
  integer :: p, k, j, i, idx1, idx2, log_p, log_k, tmp, n

  n = 2 ** log_n
  do log_p = 0, log_n-1
    p = 2 ** log_p
    do log_k = log_p, 0, -1
      k = 2 ** log_k
      do j = mod(k, p), n-1-k, 2*k
        do i = 0, min(k-1, n-j-k-1)
          idx1 = i+j
          idx2 = i+j+k
          if (idx1 / (p*2) == idx2 / (p*2)) then
            if (arr(idx1) > arr(idx2)) then
              tmp = arr(idx1)
              arr(idx1) = arr(idx2)
              arr(idx2) = tmp
            end if
          end if
        end do
      end do
    end do
  end do
end subroutine
'''
    stomp_test(code, [Msg.FoundParallelisableLoop] * 2, infer = True)


def test_bitonic_sort_infer():
    code = '''
! Code ported to Fortran from: https://sortvisualizer.com/bitonicsort/
subroutine bitonic_sort(arr, log_n)
  integer, intent(inout) :: arr(0:)
  integer, intent(in) :: log_n
  integer :: i, j, k, l, log_j, log_k, tmp
  do log_k = 1, log_n
    k = 2 ** log_k
    do log_j = log_k-1, 0, -1
      j = 2 ** log_j
      do i = 0, 2 ** log_n - 1
        l = ieor(i, j)
        if (l > i) then
          if ((iand(i, k) == 0 .and. arr(i) > arr(l)) .or.   &
              (iand(i, k) /= 0 .and. arr(i) < arr(l))) then
            tmp = arr(i)
            arr(i) = arr(l)
            arr(l) = tmp
          end if
        end if
      end do
    end do
  end do
end subroutine
'''
    stomp_test(code, [Msg.FoundParallelisableLoop], infer = True)


def test_reduction_infer():
    code = '''
subroutine sub(arr, result)
  integer, intent(in) :: arr(:)
  integer, intent(out) :: result
  integer :: i, acc
  acc = 0
  do i = 1, size(arr)
    acc = acc + arr(i)
  end do
  result = acc
end subroutine
'''
    stomp_test(code, [Msg.FoundParallelisableLoop], infer = True)
