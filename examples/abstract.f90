subroutine sub(n)
  integer, intent(in) :: n
  integer :: i
  !$omp parallel do
  do i = 1, 10
    !$stomp abstract read(n)
    print *, "Hello", n
    !$stomp end abstract
  end do
end subroutine
