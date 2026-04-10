subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, tmp
  tmp = 100
  !$omp do
  do i = 1, size(arr)
    arr(i) = arr(i) + tmp
  end do
end subroutine
