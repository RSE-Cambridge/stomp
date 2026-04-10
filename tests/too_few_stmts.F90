subroutine basic(arr)
  integer, intent(inout) :: arr(:)
  arr = 0
  !$omp parallel do
  !$omp end parallel do
end subroutine
