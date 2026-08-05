! Code from: https://www.numericalmethods.in/pages/sle/02gaussJordan.html
subroutine gauss_jordan(a, n)
  real, intent(inout) :: a(:,:)
  integer, intent(in) :: n
  integer :: i, j, k
  real :: ratio
  do k = 1, n
    !$omp parallel do private(ratio)
    do i = 1, n
      if (i /= k) then
        ratio = a(i,k) / a(k,k)
        do j=1,n+1
          a(i,j) = a(i,j) - a(k,j)*ratio
        end do
      end if
    end do
  end do
end subroutine
