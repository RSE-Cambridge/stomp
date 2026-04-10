subroutine collapse(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do collapse(1)
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
end subroutine
