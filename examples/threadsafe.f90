module example
  integer :: x
  !$omp threadprivate(x)
  !$stomp threadsafe(sub)
contains
  subroutine sub()
    x = 0
  end subroutine

  subroutine main()
    !$omp parallel
    call sub()
    !$omp end parallel
  end subroutine
end module
