import hashlib
import os
from unittest.mock import MagicMock

import pytest

from cli115.exceptions import CommandLineError
from cli115.fetcher import Fetcher
from tests.client.conftest import make_dir, make_file


def _sha1(content: bytes) -> str:
    return hashlib.sha1(content).hexdigest().upper()


def _make_remote_file(chunks: list[bytes]) -> MagicMock:
    remote = MagicMock()
    remote.__enter__.return_value = remote
    remote.__exit__.return_value = False
    remote.read.side_effect = [*chunks, b""]
    return remote


def _make_directory_client(
    entries_by_parent: dict[str, list],
    chunks_by_file_id: dict[str, list[bytes]] | None = None,
    *,
    failing_ids: set[str] | None = None,
) -> MagicMock:
    client = MagicMock()

    def list_side_effect(directory):
        return entries_by_parent.get(directory.id, [])

    client.file.list.side_effect = list_side_effect

    failing_ids = failing_ids or set()
    chunks_by_file_id = chunks_by_file_id or {}

    def open_side_effect(entry, user_agent=None):
        if entry.id in failing_ids:
            raise RuntimeError("download failed")
        return _make_remote_file(chunks_by_file_id[entry.id])

    client.file.open.side_effect = open_side_effect
    return client


class TestFetchFile:
    def test_fetch_file_downloads_to_target_path(self, tmp_path):
        content = b"hello fetcher"
        remote_file = make_file(
            name="remote.bin",
            path="/remote/remote.bin",
            size=len(content),
            sha1=_sha1(content),
        )

        client = MagicMock()
        client.file.open.return_value = _make_remote_file([content])

        fetcher = Fetcher(client)
        output = tmp_path / "out.bin"
        result = fetcher.fetch(remote_file, str(output), check_integrity=True)

        assert result == str(output.resolve())
        assert output.read_bytes() == content
        client.file.open.assert_called_once_with(remote_file, user_agent=None)
        assert len(fetcher.entries) == 1

    def test_fetch_file_emits_progress_message_and_completion_events(self, tmp_path):
        content = b"abcdef"
        remote_file = make_file(
            name="event.bin",
            path="/remote/event.bin",
            size=len(content),
            sha1=_sha1(content),
        )

        client = MagicMock()
        client.file.open.return_value = _make_remote_file([content[:2], content[2:]])

        fetcher = Fetcher(client)
        events = {
            "messages": [],
            "download_started": 0,
            "completed": 0,
            "progress": [],
        }

        def on_message(sender, message) -> None:
            events["messages"].append(message)

        def on_download(sender, progress) -> None:
            events["download_started"] += 1

            def on_change(sender, **kw) -> None:
                events["progress"].append((kw["new"], kw["completed"]))

            progress.on_change.connect(on_change, weak=False)

        def on_complete(sender) -> None:
            events["completed"] += 1

        def on_added(sender, entries) -> None:
            entry = entries[0]
            entry.status.on_message.connect(on_message, weak=False)
            entry.status.on_download.connect(on_download, weak=False)
            entry.status.on_complete.connect(on_complete, weak=False)

        fetcher.on_entry_added.connect(on_added, weak=False)
        fetcher.fetch(remote_file, str(tmp_path / "event.bin"))

        assert events["download_started"] == 1
        assert events["completed"] == 1
        assert "downloading..." in events["messages"]
        assert "download completed" in events["messages"]
        assert any(completed for _, completed in events["progress"])

    def test_fetch_file_integrity_error_removes_partial_file(self, tmp_path):
        content = b"broken"
        remote_file = make_file(
            name="broken.bin",
            path="/remote/broken.bin",
            size=len(content),
            sha1="BADSHA1",
        )

        client = MagicMock()
        client.file.open.return_value = _make_remote_file([content])

        fetcher = Fetcher(client)
        output = tmp_path / "broken.bin"

        with pytest.raises(CommandLineError, match="sha1 mismatch"):
            fetcher.fetch(remote_file, str(output), check_integrity=True)

        assert not output.exists()


class TestFetchDirectory:
    def test_fetch_directory_honors_include_and_exclude_patterns(self, tmp_path):
        root = make_dir(name="root", id="10", path="/remote/root")
        sub = make_dir(name="sub", id="11", parent_id="10", path="/remote/root/sub")

        keep_content = b"keep"
        skip_content = b"skip"
        nested_content = b"nest"

        keep_file = make_file(
            name="keep.txt",
            id="20",
            parent_id="10",
            path="/remote/root/keep.txt",
            size=len(keep_content),
            sha1=_sha1(keep_content),
        )
        skip_file = make_file(
            name="skip.log",
            id="21",
            parent_id="10",
            path="/remote/root/skip.log",
            size=len(skip_content),
            sha1=_sha1(skip_content),
        )
        nested_file = make_file(
            name="nested.txt",
            id="22",
            parent_id="11",
            path="/remote/root/sub/nested.txt",
            size=len(nested_content),
            sha1=_sha1(nested_content),
        )

        client = _make_directory_client(
            {
                root.id: [sub, keep_file, skip_file],
                sub.id: [nested_file],
            },
            {
                keep_file.id: [keep_content],
                skip_file.id: [skip_content],
                nested_file.id: [nested_content],
            },
        )

        output_dir = tmp_path / "downloads"
        output_dir.mkdir()

        fetcher = Fetcher(client)
        result = fetcher.fetch(
            root,
            str(output_dir),
            include=["**/*.txt"],
            exclude=["sub/**"],
        )

        expected_root = output_dir / "root"
        assert result == str(expected_root.resolve())
        assert (expected_root / "keep.txt").exists()
        assert not (expected_root / "skip.log").exists()
        assert not (expected_root / "sub" / "nested.txt").exists()
        assert client.file.open.call_count == 1
        assert len(fetcher.entries) == 1

    def test_fetch_directory_no_target_dir_uses_destination_directly(self, tmp_path):
        root = make_dir(name="root", id="30", path="/remote/root")
        one_file = make_file(
            name="one.txt",
            id="31",
            parent_id="30",
            path="/remote/root/one.txt",
            size=3,
            sha1=_sha1(b"one"),
        )

        client = _make_directory_client({root.id: [one_file]})

        output_dir = tmp_path / "dest"
        output_dir.mkdir()

        fetcher = Fetcher(client, dry_run=True)
        result = fetcher.fetch(root, str(output_dir), no_target_dir=True)

        assert result == str(output_dir.resolve())
        assert len(fetcher.entries) == 1
        assert fetcher.entries[0].local_path == os.path.join(
            str(output_dir.resolve()), "one.txt"
        )
        client.file.open.assert_not_called()

    def test_fetch_directory_records_errors_and_continues(self, tmp_path):
        root = make_dir(name="root", id="40", path="/remote/root")
        bad_file = make_file(
            name="bad.txt",
            id="41",
            parent_id="40",
            path="/remote/root/bad.txt",
            size=3,
            sha1=_sha1(b"bad"),
        )
        ok_file = make_file(
            name="ok.txt",
            id="42",
            parent_id="40",
            path="/remote/root/ok.txt",
            size=2,
            sha1=_sha1(b"ok"),
        )

        client = _make_directory_client(
            {root.id: [bad_file, ok_file]},
            {ok_file.id: [b"ok"]},
            failing_ids={bad_file.id},
        )

        output_dir = tmp_path / "out"

        fetcher = Fetcher(client)
        result = fetcher.fetch(root, str(output_dir), no_target_dir=True)

        assert result == str(output_dir.resolve())
        by_id = {entry.remote_entry.id: entry for entry in fetcher.entries}
        assert str(by_id[bad_file.id].error) == "download failed"
        assert by_id[ok_file.id].error is None
        assert (output_dir / "ok.txt").exists()
