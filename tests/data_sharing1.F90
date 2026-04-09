subroutine basic(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do shared(i)
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
  !$omp end parallel do
end subroutine
