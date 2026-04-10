subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, tmp
  !$omp parallel do private(tmp)
  do i = 1, size(arr)
    arr(i) = arr(i) + tmp
  end do
  !$omp end parallel do
end subroutine
