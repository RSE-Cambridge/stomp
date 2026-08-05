! Compute the prefix sums of chunks of the given array
! (a first step to computing the full parallel prefix sum)
subroutine prefix_sum_chunks(arr)
  integer, intent(inout) :: arr(:)
  integer :: chunk_size, chunk_begin, chunk_end, acc

  !$omp parallel
    ! The number of chunks is equal to the number of threads
    !$omp single
      chunk_size = omp_get_num_threads() / size(arr)
    !$omp end single

    ! Compute the prefix sum of each chunk
    !$omp do private(chunk_end, acc)
    do chunk_begin = 1, size(arr), chunk_size
      chunk_end = min(chunk_begin+chunk_size, size(arr))
      acc = 0
      do i = chunk_begin, chunk_end
        acc = acc + arr(i)
        arr(i) = acc
      end do
    end do
  !$omp end parallel
end subroutine
