subroutine basic(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel shared(i)
  !$omp do
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
  !$omp end parallel
end subroutine
