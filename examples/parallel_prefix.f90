! Example for trying the '--infer' flag

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

