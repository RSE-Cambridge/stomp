subroutine sub()
  integer :: i, n
  !$omp parallel do
  do i = 1, 10
    !$stomp abstract read(n)
    print *, "Hello", n
    !$stomp end abstract
  end do
end subroutine
