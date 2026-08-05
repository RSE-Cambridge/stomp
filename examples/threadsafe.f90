module example
  integer :: x
  !$omp threadprivate(x)
  !$stomp threadsafe(sub)
contains
  subroutine sub()
    x = x + 1
  end subroutine

  subroutine main()
    !$omp parallel
    call sub()
    !$omp end parallel
  end subroutine
end module
