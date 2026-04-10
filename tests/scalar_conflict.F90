subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, s
  s = 0
  !$omp parallel do
  do i = 1, 10
      arr(i) = 100
      s = 100
  end do
end subroutine
