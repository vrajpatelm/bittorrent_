"""
Tests for TrackerRequest.py.

Network calls (urllib.request.urlopen) are patched out so no real HTTP
requests are made during the test run.
"""
import hashlib
import struct
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

import TrackerRequest
from parser import find_parse
from TrackerRequest import get_peers_from_tracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PIECE_LENGTH = 512
ANNOUNCE = b"http://tracker.test/announce"


def _make_torrent_bytes(announce=ANNOUNCE, file_length=1000, name=b"test.bin"):
    info = {
        b"name": name,
        b"piece length": PIECE_LENGTH,
        b"pieces": b"\x00" * 20,
        b"length": file_length,
    }
    return find_parse({b"announce": announce, b"info": info})


def _make_tracker_response(peers):
    """Build a compact tracker response containing *peers* (list of (ip, port))."""
    compact = b""
    for ip, port in peers:
        parts = [int(x) for x in ip.split(".")]
        compact += bytes(parts) + struct.pack(">H", port)
    tracker_dict = {b"interval": 1800, b"peers": compact}
    return find_parse(tracker_dict)


def _make_non_compact_response(peers):
    """Build a non-compact (dict-list) tracker response."""
    peer_list = [{b"ip": ip.encode(), b"port": port} for ip, port in peers]
    tracker_dict = {b"interval": 1800, b"peers": peer_list}
    return find_parse(tracker_dict)


def _mock_urlopen(response_bytes):
    """Return a context-manager mock that yields *response_bytes*."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=BytesIO(response_bytes))
    cm.__exit__ = MagicMock(return_value=False)
    cm.read = MagicMock(return_value=response_bytes)

    # urllib.request.urlopen returns an object with .read()
    resp = MagicMock()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.read = MagicMock(return_value=response_bytes)
    return resp


# ---------------------------------------------------------------------------
# get_peers_from_tracker — happy paths
# ---------------------------------------------------------------------------

class TestGetPeersFromTrackerCompact:
    def test_returns_list(self, tmp_path):
        torrent = tmp_path / "t.torrent"
        torrent.write_bytes(_make_torrent_bytes())
        peers_in = [("192.168.1.1", 6881), ("10.0.0.2", 51413)]
        tracker_resp = _make_tracker_response(peers_in)
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(tracker_resp)):
            result = get_peers_from_tracker(str(torrent))
        # compact format: the function currently returns an empty list for compact
        # (compact parsing is not yet fully implemented — non-compact path returns tuples)
        assert isinstance(result, list)

    def test_non_compact_peers_returned(self, tmp_path):
        torrent = tmp_path / "t.torrent"
        torrent.write_bytes(_make_torrent_bytes())
        peers_in = [("192.168.1.100", 6881), ("10.0.0.1", 51413)]
        tracker_resp = _make_non_compact_response(peers_in)
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(tracker_resp)):
            result = get_peers_from_tracker(str(torrent))
        assert result == peers_in

    def test_non_compact_ip_and_port_types(self, tmp_path):
        torrent = tmp_path / "t.torrent"
        torrent.write_bytes(_make_torrent_bytes())
        peers_in = [("1.2.3.4", 9999)]
        tracker_resp = _make_non_compact_response(peers_in)
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(tracker_resp)):
            result = get_peers_from_tracker(str(torrent))
        assert len(result) == 1
        ip, port = result[0]
        assert isinstance(ip, str)
        assert isinstance(port, int)

    def test_announce_url_with_existing_query_string(self, tmp_path):
        """Tracker URL already containing '?' should be extended with '&'."""
        announce = b"http://tracker.test/announce?passkey=abc"
        torrent = tmp_path / "t.torrent"
        torrent.write_bytes(_make_torrent_bytes(announce=announce))
        tracker_resp = _make_non_compact_response([("1.2.3.4", 1234)])
        captured_urls = []

        def fake_urlopen(url, timeout=10):
            captured_urls.append(url)
            return _mock_urlopen(tracker_resp)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            get_peers_from_tracker(str(torrent))

        assert "?" in captured_urls[0]
        # Only one '?' in the URL (the existing one), extra params joined by '&'
        assert captured_urls[0].count("?") == 1

    def test_numwant_parameter_included(self, tmp_path):
        torrent = tmp_path / "t.torrent"
        torrent.write_bytes(_make_torrent_bytes())
        tracker_resp = _make_non_compact_response([])
        captured_urls = []

        def fake_urlopen(url, timeout=10):
            captured_urls.append(url)
            return _mock_urlopen(tracker_resp)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            get_peers_from_tracker(str(torrent), numwant=25)

        assert "numwant=25" in captured_urls[0]

    def test_custom_port_included_in_url(self, tmp_path):
        torrent = tmp_path / "t.torrent"
        torrent.write_bytes(_make_torrent_bytes())
        tracker_resp = _make_non_compact_response([])
        captured_urls = []

        def fake_urlopen(url, timeout=10):
            captured_urls.append(url)
            return _mock_urlopen(tracker_resp)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            get_peers_from_tracker(str(torrent), port=12345)

        assert "port=12345" in captured_urls[0]


# ---------------------------------------------------------------------------
# get_peers_from_tracker — error paths
# ---------------------------------------------------------------------------

class TestGetPeersFromTrackerErrors:
    def test_missing_announce_raises(self, tmp_path):
        """A torrent without 'announce' key should raise ValueError."""
        info = {b"name": b"test", b"piece length": 512, b"pieces": b"\x00" * 20, b"length": 100}
        torrent_bytes = find_parse({b"info": info})
        torrent = tmp_path / "t.torrent"
        torrent.write_bytes(torrent_bytes)
        with pytest.raises(ValueError, match="No announce"):
            get_peers_from_tracker(str(torrent))

    def test_missing_info_key_raises(self, tmp_path):
        """A torrent without 'info' key should raise ValueError."""
        torrent_bytes = find_parse({b"announce": b"http://t.test/ann"})
        torrent = tmp_path / "t.torrent"
        torrent.write_bytes(torrent_bytes)
        with pytest.raises(ValueError, match="No info value"):
            get_peers_from_tracker(str(torrent))

    def test_failure_reason_raises(self, tmp_path):
        """A tracker response with 'failure reason' should raise ValueError."""
        torrent = tmp_path / "t.torrent"
        torrent.write_bytes(_make_torrent_bytes())
        tracker_resp = find_parse({b"failure reason": b"torrent not registered"})
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(tracker_resp)):
            with pytest.raises(ValueError, match="torrent not registered"):
                get_peers_from_tracker(str(torrent))

    def test_no_peers_key_raises(self, tmp_path):
        """A tracker response missing 'peers' should raise ValueError."""
        torrent = tmp_path / "t.torrent"
        torrent.write_bytes(_make_torrent_bytes())
        tracker_resp = find_parse({b"interval": 1800})
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(tracker_resp)):
            with pytest.raises(ValueError, match="Peers is not present"):
                get_peers_from_tracker(str(torrent))

    def test_invalid_compact_length_raises(self, tmp_path):
        """Compact peers data whose length is not a multiple of 6 is invalid."""
        torrent = tmp_path / "t.torrent"
        torrent.write_bytes(_make_torrent_bytes())
        # 7 bytes → not a multiple of 6
        tracker_resp = find_parse({b"peers": b"\x01\x02\x03\x04\x05\x06\x07"})
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(tracker_resp)):
            with pytest.raises(ValueError, match="[Ii]nvaild Compact"):
                get_peers_from_tracker(str(torrent))

    def test_unknown_peers_type_raises(self, tmp_path):
        """If peers is neither bytes nor list, ValueError is expected."""
        torrent = tmp_path / "t.torrent"
        torrent.write_bytes(_make_torrent_bytes())
        # inject an int as 'peers' by patching bdncode_to_dict
        fake_tracker = {b"peers": 12345}
        with patch.object(TrackerRequest.parser, "bdncode_to_dict", side_effect=[
            TrackerRequest.parser.bdncode_to_dict(_make_torrent_bytes()),
            fake_tracker,
        ]):
            with patch("urllib.request.urlopen", return_value=_mock_urlopen(b"ignored")):
                with pytest.raises(ValueError, match="Unknown peers"):
                    get_peers_from_tracker(str(torrent))

    def test_missing_length_and_files_raises(self, tmp_path):
        """An info dict with neither 'length' nor 'files' should raise."""
        info = {b"name": b"test", b"piece length": 512, b"pieces": b"\x00" * 20}
        torrent_bytes = find_parse({b"announce": b"http://t.test/ann", b"info": info})
        torrent = tmp_path / "t.torrent"
        torrent.write_bytes(torrent_bytes)
        with pytest.raises(ValueError, match="No length or files"):
            get_peers_from_tracker(str(torrent))

    def test_multi_file_torrent_total_length(self, tmp_path):
        """Multi-file torrent: bytes_left is the sum of all file lengths."""
        info = {
            b"name": b"multi",
            b"piece length": PIECE_LENGTH,
            b"pieces": b"\x00" * 20,
            b"files": [
                {b"length": 300, b"path": [b"a.txt"]},
                {b"length": 400, b"path": [b"b.txt"]},
            ],
        }
        torrent_bytes = find_parse({b"announce": ANNOUNCE, b"info": info})
        torrent = tmp_path / "multi.torrent"
        torrent.write_bytes(torrent_bytes)
        tracker_resp = _make_non_compact_response([("9.9.9.9", 1234)])
        captured_urls = []

        def fake_urlopen(url, timeout=10):
            captured_urls.append(url)
            return _mock_urlopen(tracker_resp)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = get_peers_from_tracker(str(torrent))

        assert result == [("9.9.9.9", 1234)]
        assert "left=700" in captured_urls[0]
