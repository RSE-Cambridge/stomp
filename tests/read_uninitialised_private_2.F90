subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, tmp
  tmp = 100
  !$omp parallel shared(tmp)
  !$omp do private(tmp)
  do i = 1, size(arr)
    arr(i) = arr(i) + tmp
  end do
  !$omp end parallel
end subroutine
