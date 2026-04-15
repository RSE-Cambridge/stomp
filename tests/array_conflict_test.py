from stomp.test_helpers import stomp_test, Msg


def test_reverse_correct():
    code = '''
subroutine reverse(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, n, tmp
  n = size(arr)
  !$omp parallel do private(tmp)
  do i = 1, n/2
    tmp = arr(i)
    arr(i) = arr(n+1-i)
    arr(n+1-i) = tmp
  end do
end subroutine
'''
    stomp_test(code, [])


def test_reverse_incorrect():
    code = '''
subroutine reverse(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, n, tmp
  n = size(arr)
  !$omp parallel do private(tmp)
  do i = 1, n
    tmp = arr(i)
    arr(i) = arr(n+1-i)
    arr(n+1-i) = tmp
  end do
end subroutine
'''
    stomp_test(code, [Msg.LoopArrayConflict])
