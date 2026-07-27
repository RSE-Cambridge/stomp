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
    stomp_test(code, [Msg.ScalarDataRace])


def test_loop_scalar_threadprivate():
    code = '''
module m
  !$omp threadprivate(s)
  integer :: s
contains
  subroutine sub(arr)
    integer, intent(inout) :: arr(:)
    integer :: i
    !$omp parallel do private(s)
    do i = 1, 10
        arr(i) = 100
        s = 100
    end do
  end subroutine
end module
'''
    stomp_test(code, [])


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


def test_barrier_non_team_private():
    # The barrier does not prevent the data race here because it is in
    # a teams region and the data being accesses is not team-private
    code = '''
subroutine sub(arr)
  integer :: team, thread, arr(:)

  !$omp target teams
  !$omp parallel private(team, thread)
    team = omp_get_team_num()
    thread = omp_get_thread_num()
    if (team == 0) then
      arr(thread) = 1
    end if
    !$omp barrier
    if (team == 1) then
      arr(thread) = 1
    end if
  !$omp end parallel
  !$omp end target teams
endsubroutine
'''
    stomp_test(code, [Msg.ArrayDataRace])


def test_reduction_var_race_1():
    # A reduction clause implies an implict write access, which can
    # lead to a data race
    code = '''
subroutine sub()
  integer :: arr(10)
  integer :: a, i
  !$omp parallel
    !$omp master
    a = 0
    !$omp end master

    !$omp do reduction(+:a)
    do i = 1, 10
        a = a+arr(i)
    end do
    !$omp end do
  !$omp end parallel
end subroutine'''
    stomp_test(code, [Msg.ScalarDataRace])


def test_reduction_var_race_2():
    # A reduction clause implies an implict write access, which can
    # lead to a data race, but the data race can be avoided with a barrier.
    code = '''
subroutine sub()
  integer :: arr(10)
  integer :: a, i
  !$omp parallel
    !$omp master
    a = 0
    !$omp end master

    !$omp barrier

    !$omp do reduction(+:a)
    do i = 1, 10
        a = a+arr(i)
    end do
    !$omp end do
  !$omp end parallel
end subroutine'''
    stomp_test(code, [])


def test_reduction_var_race_3():
    # A reduction clause implies an implict write access, which can
    # lead to a data race with a subsequent access if there is a nowait
    # clause
    code = '''
subroutine sub()
  integer :: arr(10)
  integer :: a, i
  !$omp parallel
    !$omp master
    a = 0
    !$omp end master

    !$omp barrier

    !$omp do reduction(+:a)
    do i = 1, 10
        a = a+arr(i)
    end do
    !$omp end do nowait

    !$omp master
    a = a+1
    !$omp end master
  !$omp end parallel
end subroutine'''
    stomp_test(code, [Msg.ScalarDataRace])


def test_reduction_var_race_4():
    # A reduction clause implies an implict write access, which can
    # lead to a data race with a subsequent access if there is a nowait
    # clause, but can be avoided using a barrier.
    code = '''
subroutine sub()
  integer :: arr(10)
  integer :: a, i
  !$omp parallel
    !$omp master
    a = 0
    !$omp end master

    !$omp barrier

    !$omp do reduction(+:a)
    do i = 1, 10
        a = a+arr(i)
    end do
    !$omp end do nowait

    !$omp barrier

    !$omp master
    a = a+1
    !$omp end master
  !$omp end parallel
end subroutine'''
    stomp_test(code, [])
