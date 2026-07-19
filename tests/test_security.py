from sirchatalot.config import UrlOpenConfig
from sirchatalot.tg.handlers import sanitize_filename
from sirchatalot.tools.web import UrlOpener


def test_sanitize_filename_traversal():
    assert '/' not in sanitize_filename('../../etc/passwd')
    assert sanitize_filename('../../etc/passwd') == 'passwd'
    assert sanitize_filename('..\\..\\boot.ini').endswith('boot.ini')


def test_sanitize_filename_hidden_and_empty():
    for bad in ('.bashrc', '', None, '...', '/'):
        name = sanitize_filename(bad)
        assert name and not name.startswith('.') and '/' not in name


def test_sanitize_filename_normal():
    assert sanitize_filename('report (final).pdf') == 'report (final).pdf'
    assert sanitize_filename('отчёт 2026.docx') == 'отчёт 2026.docx'


async def test_url_opener_rejects_unsafe():
    opener = UrlOpener(UrlOpenConfig())
    assert await opener.check_url('file:///etc/passwd') is not None
    assert await opener.check_url('ftp://example.com/x') is not None
    assert await opener.check_url('http://localhost/admin') is not None
    assert await opener.check_url('http://127.0.0.1:8080/') is not None
    assert await opener.check_url('http://169.254.169.254/latest/meta-data/') is not None
    assert await opener.check_url('http://[::1]/') is not None
    assert await opener.check_url('http://10.0.0.5/internal') is not None
    assert await opener.check_url('https://') is not None
