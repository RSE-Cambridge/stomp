subroutine odd_even_transposition(arr, start)
  integer , intent(inout) :: arr(:)
  integer, intent(in) :: start
  integer :: i, tmp
  !$omp parallel do private(tmp)
  do i = start, size(arr)-1, 2
    if (arr(i) > arr(i+1)) then
      tmp = arr(i+1)
      arr(i+1) = arr(i)
      arr(i) = tmp
    end if
  end do
end subroutine
