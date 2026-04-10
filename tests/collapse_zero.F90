subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do collapse(0)
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
end subroutine
