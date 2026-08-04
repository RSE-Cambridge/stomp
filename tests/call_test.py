# SPDX-License-Identifier: BSD-3-Clause

from stomp.test_helpers import stomp_test, Msg


def test_impure_call():
    '''Test that a routine not declared as "pure" triggers
    an ImpureParallelCall issue when called from a parallel region.'''
    code = '''
module m
contains
  subroutine sub()
  end subroutine

  subroutine main()
    !$omp parallel
    call sub()
    !$omp end parallel
  end subroutine
end module
'''
    stomp_test(code, [Msg.ImpureParallelCall])


def test_pure_call():
    '''Test that a routine not declared as "pure" triggers
    an ImpureParallelCall issue when called from a parallel region.'''
    code = '''
module m
contains
  pure subroutine sub()
  end subroutine

  subroutine main()
    !$omp parallel
    call sub()
    !$omp end parallel
  end subroutine
end module
'''
    stomp_test(code, [])


def test_threadsafe():
    '''Test that a routine declared as "threadsafe" does not trigger
    an ImpureParallelCall issue when called from a parallel region.'''
    code = '''
module m
  !$stomp threadsafe(sub)
contains
  subroutine sub()
  end subroutine

  subroutine main()
    !$omp parallel
    call sub()
    !$omp end parallel
  end subroutine
end module
'''
    stomp_test(code, [])
