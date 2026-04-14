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
