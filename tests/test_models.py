import io
from unittest.mock import MagicMock

import pytest

from cli115.client.models import Progress, UploadStatus
from cli115.client.webapi.file import patch_filelike


class TestProgress:
    def test_initial_state(self):
        p = Progress(1000)
        assert p.total_bytes == 1000
        assert p.completed_bytes == 0
        assert not p.is_started()
        assert not p.is_completed()
        assert not p.is_failed()

    def test_start(self):
        p = Progress(1000)
        p.start()
        assert p.is_started()

    def test_update_partial(self):
        p = Progress(1000)
        p.update(500)
        assert p.completed_bytes == 500
        assert not p.is_completed()

    def test_update_complete(self):
        p = Progress(1000)
        p.update(1000)
        assert p.completed_bytes == 1000
        assert p.is_completed()

    def test_update_beyond_total_clamps(self):
        p = Progress(1000)
        p.update(2000)
        assert p.completed_bytes == 1000

    def test_complete(self):
        p = Progress(1000)
        p.start()
        p.complete()
        assert p.is_completed()
        assert p.duration.total_seconds() >= 0

    def test_failed(self):
        p = Progress(1000)
        p.start()
        p.failed()
        assert p.is_failed()
        assert not p.is_completed()

    def test_on_change_signal_fired_on_update(self):
        p = Progress(1000)
        receiver = MagicMock()
        p.on_change.connect(receiver)
        p.update(100)
        receiver.assert_called_once_with(p)

    def test_on_change_signal_fired_on_complete(self):
        p = Progress(1000)
        receiver = MagicMock()
        p.on_change.connect(receiver)
        p.complete()
        receiver.assert_called_once_with(p)

    def test_on_change_signal_fired_on_failed(self):
        p = Progress(1000)
        receiver = MagicMock()
        p.on_change.connect(receiver)
        p.failed()
        receiver.assert_called_once_with(p)

    def test_context_manager_completes_on_success(self):
        with Progress(1000) as p:
            p.update(1000)
        assert p.is_completed()

    def test_context_manager_fails_on_exception(self):
        with pytest.raises(RuntimeError):
            with Progress(1000) as p:
                raise RuntimeError("boom")
        assert p.is_failed()

    def test_duration_zero_before_start(self):
        p = Progress(1000)
        assert p.duration.total_seconds() == 0


class TestUploadStatus:
    def test_initial_state(self):
        s = UploadStatus()
        assert s.use_instant_upload is None
        assert s.is_instant_uploaded is None
        assert s.instant_upload_error is None
        assert s.progress is None
        assert not s.is_completed

    def test_use_instant_upload_setter_fires_signal(self):
        s = UploadStatus()
        receiver = MagicMock()
        s.on_update.connect(receiver)
        s.use_instant_upload = True
        receiver.assert_called_once()
        _, kwargs = receiver.call_args
        assert kwargs["field"] == "use_instant_upload"
        assert kwargs["value"] is True

    def test_is_instant_uploaded_setter_fires_signal(self):
        s = UploadStatus()
        receiver = MagicMock()
        s.on_update.connect(receiver)
        s.is_instant_uploaded = False
        receiver.assert_called_once()
        _, kwargs = receiver.call_args
        assert kwargs["field"] == "is_instant_uploaded"
        assert kwargs["value"] is False
        assert not s.is_completed

    def test_is_instant_uploaded_true_marks_completed(self):
        s = UploadStatus()
        receiver = MagicMock()
        s.on_complete.connect(receiver)

        s.is_instant_uploaded = True

        assert s.is_completed
        receiver.assert_called_once_with(s)

    def test_instant_upload_error_setter_fires_signal(self):
        s = UploadStatus()
        receiver = MagicMock()
        s.on_update.connect(receiver)
        err = ValueError("oops")
        s.instant_upload_error = err
        receiver.assert_called_once()
        _, kwargs = receiver.call_args
        assert kwargs["field"] == "instant_upload_error"
        assert kwargs["value"] is err

    def test_progress_setter_fires_signal(self):
        s = UploadStatus()
        receiver = MagicMock()
        s.on_update.connect(receiver)
        p = Progress(500)
        s.progress = p
        receiver.assert_called_once()
        _, kwargs = receiver.call_args
        assert kwargs["field"] == "progress"
        assert kwargs["value"] is p

    def test_progress_change_propagates_to_on_update(self):
        s = UploadStatus()
        p = Progress(500)
        s.progress = p

        receiver = MagicMock()
        s.on_update.connect(receiver)
        p.update(250)

        receiver.assert_called_once()
        _, kwargs = receiver.call_args
        assert kwargs["field"] == "progress"
        assert kwargs["value"] is p

    def test_progress_completion_marks_completed(self):
        s = UploadStatus()
        p = Progress(500)
        receiver = MagicMock()
        s.on_complete.connect(receiver)

        s.progress = p
        p.update(500)

        assert s.is_completed
        receiver.assert_called_once_with(s)

    def test_on_complete_emitted_once(self):
        s = UploadStatus()
        receiver = MagicMock()
        s.on_complete.connect(receiver)

        p = Progress(500)
        s.progress = p
        s.is_instant_uploaded = True
        p.update(500)

        receiver.assert_called_once_with(s)


class TestPatchFilelike:
    def test_read_updates_progress(self):
        data = b"hello world"
        file = io.BytesIO(data)
        p = Progress(len(data))

        with patch_filelike(file, p):
            chunk = file.read(5)

        assert chunk == b"hello"
        assert p.completed_bytes == 5

    def test_full_read_updates_progress(self):
        data = b"hello world"
        file = io.BytesIO(data)
        p = Progress(len(data))

        with patch_filelike(file, p):
            chunk = file.read()

        assert chunk == data
        assert p.completed_bytes == len(data)

    def test_original_read_restored_after_context(self):
        data = b"test data"
        file = io.BytesIO(data)
        original_read = file.read
        p = Progress(len(data))

        with patch_filelike(file, p):
            patched_read = file.read
            assert patched_read is not original_read

        assert file.read == original_read

    def test_original_read_restored_on_exception(self):
        data = b"test data"
        file = io.BytesIO(data)
        original_read = file.read
        p = Progress(len(data))

        with pytest.raises(RuntimeError):
            with patch_filelike(file, p):
                raise RuntimeError("error during upload")

        assert file.read == original_read

    def test_on_change_signal_fired_on_read(self):
        data = b"abcde"
        file = io.BytesIO(data)
        p = Progress(len(data))
        receiver = MagicMock()
        p.on_change.connect(receiver)

        with patch_filelike(file, p):
            file.read(3)
            file.read(2)

        assert receiver.call_count == 2

    def test_multiple_reads_accumulate_progress(self):
        data = b"0123456789"
        file = io.BytesIO(data)
        p = Progress(len(data))

        with patch_filelike(file, p):
            file.read(4)
            file.read(6)

        assert p.completed_bytes == 10
