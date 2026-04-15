from stomp.test_helpers import stomp_test, Msg


def test_loop_scalar_conflict():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, s
  s = 0
  !$omp parallel do
  do i = 1, 10
      arr(i) = 100
      s = 100
  end do
end subroutine
'''
    stomp_test(code, [Msg.LoopScalarConflict])


def test_shared_loop_var_1():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do shared(i)
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
  !$omp end parallel do
end subroutine
'''
    stomp_test(code, [Msg.DataSharingConflict])


def test_shared_loop_var_2():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel shared(i)
  !$omp do
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
  !$omp end parallel
end subroutine
'''
    stomp_test(code, [Msg.DataSharingConflict])
