# SPDX-License-Identifier: BSD-3-Clause

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


def test_missing_end():
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  integer :: i
  !$omp parallel
  arr(omp_get_thread_num()) = 0
end subroutine
'''
    stomp_test(code, [Msg.MissingEnd])


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
    stomp_test(code, [Msg.MisplacedDirective])


def test_sections_malformed():
    '''Simple test of a malformed 'sections' directive.'''
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  !$omp parallel
    !$omp sections
      arr(1) = 100
    !$omp end sections
  !$omp end parallel
end subroutine
'''
    stomp_test(code, [Msg.MalformedSectionsDirective])


def test_sections_wellformed():
    '''Simple test of a well-formed 'sections' directive.'''
    code = '''
subroutine sub(arr)
  integer, intent(inout) :: arr(:)
  !$omp parallel
    !$omp sections
      ! Hello world

      !$omp section
      arr(1) = 100
    !$omp end sections
  !$omp end parallel
end subroutine
'''
    stomp_test(code, [])


def test_wildcard_import():
    '''Simple test of wildcard imports in a subroutine.'''
    code = '''
module m
contains
  subroutine sub()
    use foo
    integer :: i, arr(10)
    !$omp parallel do
    do i = 1, 10
      arr(i) = i
    end do
  end subroutine
end module
'''
    stomp_test(code, [Msg.WildcardImportInSubroutine])

def test_non_wildcard_imports():
    '''Simple test of non-wildcard imports in a subroutine.'''
    code = '''
module m
contains
  subroutine sub()
    integer :: i, arr(10)
    !$omp parallel do
    do i = 1, 10
      arr(i) = i
    end do
  end subroutine
end module
'''
    stomp_test(code, [])


def test_disallowed_nowait():
    '''Simple test of disallowed "nowait" clause.'''
    code = '''
subroutine sub()
  integer :: i, arr(10)
  !$omp parallel do
  do i = 1, 10
    arr(i) = i
  end do
  !$omp end parallel do nowait
end subroutine
'''
    stomp_test(code, [Msg.BadNowait])

def test_misplaced_barrier():
    '''Simple test of misplaced "barrier" directive.'''
    code = '''
subroutine sub()
  integer :: i, arr(10)
  !$omp teams private(i)
    i = 100
    !$omp barrier
    i = 101
  !$omp end teams
end subroutine
'''
    stomp_test(code, [Msg.MisplacedDirective])


def test_codeblock_in_parallel_region():
    '''Simple test of a PSyIR CodeBlock in a parallel region.'''
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
    print *, "Hello"
  end do
end subroutine
'''
    stomp_test(code, [Msg.PSyIRLimitation])


def test_stomp_abstract():
    '''Simple test of a stomp 'abstract' directive.'''
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
    !$stomp abstract read(n)
    print *, "Hello", n
    !$stomp end abstract
  end do
end subroutine
'''
    stomp_test(code, [])
