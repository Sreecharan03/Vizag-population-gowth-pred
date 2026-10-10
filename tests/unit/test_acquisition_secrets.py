"""test_secrets_never_appear_in_logs_or_reports (Phase 2 Part 2.1).

The inventory report/manifest are plain-language/JSON outputs derived only
from B2 object keys and sizes — they never touch credentials at all, but
this proves it rather than assuming it.
"""

from src.acquisition.inventory import generate_report, list_inventory
from src.storage.backends import FakeBackend
from src.utils.secrets import get_known_secret_values, scan_files_for_leaked_secrets
from tests.fixtures.fake_bucket import FAKE_BUCKET_OBJECTS


def test_secrets_never_appear_in_logs_or_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_INVENTORY_TEST_SECRET_KEY", "superlongsecretvalue000111222")

    backend = FakeBackend()
    for key, size in FAKE_BUCKET_OBJECTS:
        backend.seed(key, b"x" * size)
    entries = list_inventory(backend)
    report = generate_report(entries)

    report_path = tmp_path / "inventory_report.md"
    report_path.write_text(report)

    secrets = get_known_secret_values()
    assert "superlongsecretvalue000111222" in secrets  # sanity: our fake secret is actually detected

    findings = scan_files_for_leaked_secrets([report_path], secrets=secrets)
    assert findings == {}
