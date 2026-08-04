# SPDX-License-Identifier: BSD-3-Clause

from stomp.test_helpers import stomp_test, Msg


def test_simple_reduction_ok():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, total
  !$omp parallel do reduction(+: total)
  do i = 1, n
    total = total + arr(i)
  end do
end subroutine
'''
    stomp_test(code, [])


def test_simple_reduction_wrong_op():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, total
  !$omp parallel do reduction(*: total)
  do i = 1, n
    total = total + arr(i)
  end do
end subroutine
'''
    stomp_test(code, [Msg.BadReductionClause])


def test_simple_reduction_bad_ref():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, total
  !$omp parallel do reduction(+: total)
  do i = 1, n
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [Msg.BadReductionClause])


def test_simple_array_reduction():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, total(10)
  !$omp parallel do reduction(+: total)
  do i = 1, n
    total = total + arr(i)
  end do
end subroutine
'''
    stomp_test(code, [Msg.UnsupportedArrayReduction])


def test_simple_non_reduction():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, total
  !$omp parallel do reduction(+: total)
  do i = 1, n
    total = arr(i)
  end do
end subroutine
'''
    stomp_test(code, [Msg.BadReductionClause])
