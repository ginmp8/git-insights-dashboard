from gitinsights.analytics import recent_activity


def test_recent_commit_order_handles_different_author_timezones():
    # Both ISO strings are individually valid but lexicographic order would be wrong.
    earlier = {'date': '2025-01-01T10:00:00+03:00', 'sha': 'a' * 40, 'author': 'A',
               'email': 'a@demo.local', 'message': 'earlier', 'files': []}
    later = {'date': '2025-01-01T06:30:00-02:00', 'sha': 'b' * 40, 'author': 'B',
             'email': 'b@demo.local', 'message': 'later', 'files': []}
    assert [c['message'] for c in recent_activity([earlier, later])] == ['later', 'earlier']
