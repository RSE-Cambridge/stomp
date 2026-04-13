subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, tmp
  !$omp parallel private(tmp)
  tmp = 100
  !$omp do
  do i = 1, size(arr)
    arr(i) = arr(i) + tmp
  end do
  !$omp end parallel
end subroutine
