# SPDX-License-Identifier: BSD-4-Clause

from stomp.test_helpers import stomp_test, Msg


def test_bounds_1_ok():
    code = '''
subroutine inc(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [], check_bounds=True)


def test_bounds_2_bad():
    code = '''
subroutine inc(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do
  do i = 0, size(arr)
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [Msg.OutOfBounds], check_bounds=True)


def test_bounds_3_bad():
    code = '''
subroutine inc(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do
  do i = 1, size(arr)+1
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [Msg.OutOfBounds], check_bounds=True)


def test_bounds_4_ok():
    code = '''
subroutine inc(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel do
  do i = lbound(arr, 1), ubound(arr, 1)
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [], check_bounds=True)


def test_bounds_5_ok():
    code = '''
subroutine inc(arr)
  integer, intent(inout) :: arr(2:)
  integer :: i
  !$omp parallel do
  do i = 2, ubound(arr, 1)
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [], check_bounds=True)


def test_bounds_6_bad():
    code = '''
subroutine inc(arr)
  integer, intent(inout) :: arr(2:)
  integer :: i
  !$omp parallel do
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [Msg.OutOfBounds], check_bounds=True)


def test_bounds_7_ok():
    code = '''
subroutine inc(arr)
  integer, intent(inout) :: arr(2:10)
  integer :: i
  !$omp parallel do
  do i = lbound(arr, 1), 10
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [], check_bounds=True)


def test_bounds_8_bad():
    code = '''
subroutine inc(arr)
  integer, intent(inout) :: arr(2:10)
  integer :: i
  !$omp parallel do
  do i = lbound(arr, 1), 11
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [Msg.OutOfBounds], check_bounds=True)


def test_bounds_9_ok():
    code = '''
subroutine inc(arr, n)
  integer, intent(in) :: n
  integer, intent(inout) :: arr(n)
  integer :: i
  !$omp parallel do
  do i = 1, n
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [], check_bounds=True)


def test_bounds_10_ok():
    code = '''
subroutine inc(arr, n)
  integer, intent(in) :: n
  integer, intent(inout) :: arr(n)
  integer :: i
  !$omp parallel do
  do i = 1, size(arr)
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [], check_bounds=True)


def test_bounds_11_bad():
    code = '''
subroutine inc(arr, n)
  integer, intent(in) :: n
  integer, intent(inout) :: arr(n)
  integer :: i
  !$omp parallel do
  do i = 1, n+1
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [Msg.OutOfBounds], check_bounds=True)


def test_bounds_12_bad():
    code = '''
subroutine inc(arr)
  integer, allocatable, intent(inout) :: arr(:)
  integer :: i, n
  allocate(arr(10))
  n = size(arr)
  allocate(arr(5))
  !$omp parallel do
  do i = 1, n
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [Msg.OutOfBounds], check_bounds=True)


def test_bounds_13_bad():
    code = '''
subroutine inc(arr)
  integer, allocatable, intent(inout) :: arr(:)
  integer :: i
  allocate(arr(10))
  deallocate(arr)
  !$omp parallel do
  do i = 1, 10
    arr(i) = arr(i) + 1
  end do
end subroutine
'''
    stomp_test(code, [Msg.OutOfBounds], check_bounds=True)
