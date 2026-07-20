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
    stomp_test(code, [Msg.DataRace])


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
    stomp_test(code, [Msg.DataRace])
