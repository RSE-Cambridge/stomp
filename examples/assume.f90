subroutine sub(arr, offset, n)
  integer, intent(inout) :: arr(:)
  integer, intent(in) :: n, offset
  integer :: i
  !$stomp assume (offset > n)
  !$omp parallel do
  do i = 1, n
    arr(i) = 0
    arr(offset+i) = 1
  end do
end subroutine
