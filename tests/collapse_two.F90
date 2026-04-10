subroutine collapse(arr)
  integer, intent(inout) :: arr(:,:)
  integer :: i, j
  !$omp parallel do collapse(2)
  do j = 1, size(arr,1)
    do i = 1, size(arr,2)
       arr(i, j) = arr(i, j) + 1
    end do
  end do
end subroutine
