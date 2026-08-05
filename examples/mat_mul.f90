subroutine my_matmul(a, b, c)
  integer, dimension(:,:), intent(in) :: a
  integer, dimension(:,:), intent(in) :: b
  integer, dimension(:,:), intent(out) :: c
  integer :: x, y, k, k_tile, x_tile, y_tile, chunk_size

  c(:,:) = 0
  !$omp parallel do collapse(2)
  do y_tile = 1, size(a, 2), chunk_size
    do x_tile = 1, size(b, 1), chunk_size
      do k_tile = 1, size(a, 1), chunk_size
        do y = y_tile, min(y_tile + (chunk_size - 1), size(a, 2)), 1
          do x = x_tile, min(x_tile + (chunk_size - 1), size(b, 1)), 1
            do k = k_tile, min(k_tile + (chunk_size - 1), size(a, 1)), 1
              c(x,y) = c(x,y) + a(k,y) * b(x,k)
            enddo
          enddo
        enddo
      enddo
    enddo
  enddo
end subroutine
