subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel &
  !$omp do &
  !$omp shared(arr)
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
  !$omp end parallel do
end subroutine
