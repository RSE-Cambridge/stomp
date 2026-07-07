from stomp.test_helpers import stomp_test, Msg


def test_unrecognised_directive():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  arr = 0
  !$omp wibble
end subroutine
'''
    stomp_test(code, [Msg.UnrecognisedDirective])


def test_multiline_directive():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel &
  !$omp do &
  !$omp shared(arr)
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
  !$omp end parallel do
end subroutine
'''
    stomp_test(code, [])


def test_unmatched_end():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
  !$omp end parallel
end subroutine
'''
    stomp_test(code, [Msg.UnmatchedEnd])


def test_loop_directive_has_no_loop():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do
  i = 0
end subroutine
'''
    stomp_test(code, [Msg.LoopDirectiveHasNoLoop])


def test_too_many_stmts():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
  i = 1
  !$omp end parallel do
end subroutine
'''
    stomp_test(code, [Msg.SingleStatementExpected])


def test_too_few_stmts():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  arr = 0
  !$omp parallel do
  !$omp end parallel do
end subroutine
'''
    stomp_test(code, [Msg.LoopDirectiveHasNoLoop,
                      Msg.SingleStatementExpected])

def test_double_private():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, j
  !$omp parallel private(i) private(j)
  i = 10
  j = 100
  !$omp end parallel
end subroutine
'''
    stomp_test(code, [])


def test_stray_ordered_yes():
    code = '''
subroutine sub()
  integer :: i, arr(10)
  !$omp parallel do
  do i = 1, 10
      !$omp ordered
      arr(1) = i
      !$omp end ordered
  end do
end subroutine
'''
    stomp_test(code, [Msg.StrayOrderedDirective])


def test_stray_ordered_no():
    code = '''
subroutine sub()
  integer :: i, arr(10)
  !$omp parallel do ordered
  do i = 1, 10
      !$omp ordered
      arr(1) = i
      !$omp end ordered
  end do
end subroutine
'''
    stomp_test(code, [])


def test_nested_parallelism():
    code = '''
subroutine sub()
  integer :: i, arr(10)
  !$omp parallel
    !$omp parallel do
    do i = 1, 10
      arr(i) = i
    end do
  !$omp end parallel
end subroutine
'''
    stomp_test(code, [Msg.DisallowedNestedDirective])
