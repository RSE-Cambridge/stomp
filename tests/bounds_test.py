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

def test_bounds_14_ok():
    code = '''
module m
  type :: ty
    integer :: n
    integer, allocatable :: arr(:)
  end type

  contains

  subroutine inc(x)
    type(ty), intent(inout) :: x
    integer :: i
    !$omp parallel do
    do i = lbound(x%arr, 1), ubound(x%arr, 1)
      x%arr(i) = x%arr(i) + 1
    end do
  end subroutine
end module
'''
    stomp_test(code, [], check_bounds=True)

def test_bounds_14_bad():
    code = '''
module m
  type :: ty
    integer :: n
    integer, allocatable :: arr(:)
  end type

  contains

  subroutine alloc(x)
    type(ty), intent(inout) :: x
    allocate(x%arr(1:10))
  end subroutine

  subroutine inc(x)
    type(ty), intent(inout) :: x
    integer :: i, l, u
    l = lbound(x%arr, 1)
    u = ubound(x%arr, 1)
    call alloc(x) ! This changes the bounds
    !$omp parallel do
    do i = l, u
      x%arr(i) = x%arr(i) + 1
    end do
  end subroutine
end module
'''
    stomp_test(code, [Msg.OutOfBounds], check_bounds=True)
