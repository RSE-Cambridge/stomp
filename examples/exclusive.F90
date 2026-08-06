subroutine sub(arr, indirection)
  integer, intent(inout) :: arr(:)
  integer, intent(in) :: indirection(:)
  integer :: i, j
  !$omp parallel do private(j)
  do i = 1, size(arr)
    j = indirection(i)
    if (j == 1) then
      !$stomp exclusive
      arr(j) = 1
      !$stomp end exclusive
    end if
  end do
end subroutine
