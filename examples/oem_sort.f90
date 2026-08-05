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
      !$omp parallel do private(idx1, idx2, tmp)
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
