subroutine sub(arr, lookup_table)
  integer, intent(inout) :: arr(:)
  integer, intent(in) :: lookup_table(:)
  integer :: i, j
  !$omp parallel do private(j)
  do i = 1, size(arr)
    j = lookup_table(i)
    !$stomp unique(j)
    arr(j) = 1
  end do
end subroutine
