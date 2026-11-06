import csv
import io

from gitinsights.export import csv_bytes


def test_csv_neutralizes_spreadsheet_injection():
    data = [
        {'message': '=HYPERLINK("https://evil.example")', 'author': '+cmd', 'files': 2},
        {'message': '  @SUM(1,1)', 'author': 'ordinary', 'files': 3},
    ]
    b = csv_bytes(data)
    assert b.startswith(b'\xef\xbb\xbf')
    parsed = list(csv.DictReader(io.StringIO(b.decode('utf-8-sig'))))
    assert parsed[0]['message'].startswith("'=")
    assert parsed[0]['author'] == "'+cmd"
    assert parsed[1]['message'].startswith("'  @")
    assert parsed[1]['author'] == 'ordinary'
    assert parsed[1]['files'] == '3'


def test_empty_csv_is_empty():
    assert csv_bytes([]) == b''
