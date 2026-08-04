# SPDX-License-Identifier: BSD-3-Clause

from stomp.test_helpers import stomp_test, Msg

def test_read_uninitialised_private_1():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, tmp
  !$omp parallel do private(tmp)
  do i = 1, size(arr)
    arr(i) = arr(i) + tmp
  end do
  !$omp end parallel do
end subroutine
'''
    stomp_test(code, [Msg.ReadUninitialisedPrivate])


def test_read_uninitialised_private_2():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, tmp
  tmp = 100
  !$omp parallel shared(tmp)
  !$omp do private(tmp)
  do i = 1, size(arr)
    arr(i) = arr(i) + tmp
  end do
  !$omp end parallel
end subroutine
'''
    stomp_test(code, [Msg.ReadUninitialisedPrivate])


def test_read_initialised_private_1():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, tmp
  !$omp parallel private(tmp)
  tmp = 100
  !$omp do
  do i = 1, size(arr)
    arr(i) = arr(i) + tmp
  end do
  !$omp end parallel
end subroutine
'''
    stomp_test(code, [])


def test_read_initialised_private_2():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i, tmp
  tmp = 100
  !$omp do
  do i = 1, size(arr)
    arr(i) = arr(i) + tmp
  end do
end subroutine
'''
    stomp_test(code, [])
