# SPDX-License-Identifier: BSD-3-Clause

from stomp.test_helpers import stomp_test, Msg


def test_non_rectangular_loop():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:,:)
  integer :: i, j
  !$omp parallel do collapse(2)
  do j = 1, size(arr,1)
    do i = 1, j
      arr(i, j) = arr(i, j) + 1
    end do
  end do
end subroutine
'''
    stomp_test(code, [Msg.NonRectangularLoop])


def test_collapse_zero():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do collapse(0)
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [Msg.InvalidCollapseClause])


def test_collapse_one():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do collapse(1)
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [])


def test_collapse_two():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:,:)
  integer :: i, j
  !$omp parallel do collapse(2)
  do j = 1, size(arr,1)
    do i = 1, size(arr,2)
      arr(i, j) = arr(i, j) + 1
    end do
  end do
end subroutine
'''
    stomp_test(code, [])


def test_collapse_too_many():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do collapse(2)
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [Msg.InvalidCollapseClause])
