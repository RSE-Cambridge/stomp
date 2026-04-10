subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  arr = 0
  !$omp wibble
end subroutine
