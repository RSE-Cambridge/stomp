subroutine sub(arr, lookup_table)
  integer, intent(inout) :: arr(:)
  integer, intent(in) :: lookup_table(:)
  integer :: i, j
  !$omp parallel do private(j)
  do i = 1, size(arr)
    j = lookup_table(i)
    if (j == 1) then
      !$stomp exclusive
      arr(j) = 1
      !$stomp end exclusive
    end if
  end do
end subroutine
