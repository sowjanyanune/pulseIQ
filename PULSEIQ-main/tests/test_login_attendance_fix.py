"""Regression checks for session revocation and session attendance persistence."""
from datetime import date
from test_tenants import client, signin, post, PASSWORD


def test_existing_cookie_session_is_revoked_by_logout(client):
    signin(client, 'admin@test.edu')
    assert client.get('/api/auth/me').status_code == 200
    # The React page now performs this csrf-protected logout when first loaded.
    response = client.post('/api/auth/logout')
    assert response.status_code == 200
    assert client.get('/api/auth/me').status_code == 401


def test_correctly_assigned_faculty_attendance_is_reloaded_after_save(client):
    signin(client, 'admin@test.edu')
    post(client, '/api/v4/students', {
        'student_id': 'ROLL20', 'full_name': 'Student Twenty',
        'email': 'twenty@test.edu', 'password': PASSWORD,
        'department': 'CSE', 'semester': 5, 'section': 'B'})
    faculty = post(client, '/api/admin/accounts', {
        'email': 'teacher20@test.edu', 'full_name': 'Teacher Twenty',
        'password': PASSWORD, 'role': 'faculty', 'departments': ['CSE']})
    assignment = post(client, '/api/admin/assignments', {
        'faculty_id': faculty['id'], 'department': 'CSE', 'semester': 5,
        'section': 'B', 'subject': 'Database Management'})['id']
    signin(client, 'teacher20@test.edu')
    members = client.get('/api/v4/class/' + assignment + '/students').json()['items']
    assert [x['student_id'] for x in members] == ['ROLL20']
    payload = {'assignment_id': assignment, 'on_date': date.today().isoformat(),
               'time_slot': '10:00-11:00', 'topic': 'Database normalization',
               'items': [{'student_id': 'ROLL20', 'present': False}]}
    result = post(client, '/api/v4/attendance/batch', payload)
    assert result['marked'] == 1
    reloaded = client.get('/api/v4/attendance/session', params={
        'assignment_id': assignment, 'on_date': payload['on_date'],
        'time_slot': payload['time_slot']}).json()
    assert reloaded['topic'] == 'Database normalization'
    assert reloaded['items'] == [{'student_id': 'ROLL20', 'present': False}]
