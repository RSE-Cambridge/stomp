subroutine flatten(mat, arr)
  real, intent(in) :: mat(0:,0:)
  real, intent(out) :: arr(0:)
  integer :: x, y
  integer :: nx, ny
  nx = size(mat, 1)
  ny = size(mat, 2)
  !$omp parallel do collapse(2)
  do y = 0, ny-1
    do x = 0, nx-1
      arr(nx * y + x) = mat(x, y)
    end do
  end do
end subroutine
