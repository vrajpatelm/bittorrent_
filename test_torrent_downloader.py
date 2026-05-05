"""
Tests for TorrentDownloader class in BittorrentPeer.py.

A synthetic torrent file is written to a temp directory so no real
.torrent file is needed.
"""
import asyncio
import hashlib
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from BittorrentPeer import TorrentDownloader
from parser import find_parse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PIECE_LENGTH = 512          # small value so tests stay fast
FILE_SIZE = 1500            # 3 pieces: 512 + 512 + 476


def _piece_hashes(data: bytes, piece_length: int) -> bytes:
    """Build the concatenated SHA-1 hash string for *data*."""
    pieces = b""
    for offset in range(0, len(data), piece_length):
        chunk = data[offset : offset + piece_length]
        pieces += hashlib.sha1(chunk).digest()
    return pieces


def _make_torrent_bytes(
    file_data: bytes,
    piece_length: int = PIECE_LENGTH,
    name: bytes = b"test.bin",
    announce: bytes = b"http://tracker.test/announce",
) -> bytes:
    """Return valid bencoded torrent bytes for the given file_data."""
    hashes = _piece_hashes(file_data, piece_length)
    info = {
        b"name": name,
        b"piece length": piece_length,
        b"pieces": hashes,
        b"length": len(file_data),
    }
    torrent = {b"announce": announce, b"info": info}
    return find_parse(torrent)


@pytest.fixture
def tmp_torrent(tmp_path):
    """Write a test torrent file and return (path, file_data)."""
    # Use a prime-period pattern so adjacent pieces always differ in content.
    file_data = bytes(i % 127 for i in range(FILE_SIZE))
    assert len(file_data) == FILE_SIZE
    torrent_bytes = _make_torrent_bytes(file_data)
    torrent_path = tmp_path / "test.torrent"
    torrent_path.write_bytes(torrent_bytes)
    return str(torrent_path), file_data


@pytest.fixture
def downloader(tmp_torrent):
    """Return a TorrentDownloader for the temp torrent."""
    path, _ = tmp_torrent
    return TorrentDownloader(torrent_file_path=path, peers=[])


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestTorrentDownloaderInit:
    def test_num_pieces(self, tmp_torrent, downloader):
        expected = (FILE_SIZE + PIECE_LENGTH - 1) // PIECE_LENGTH
        assert downloader.num_pieces == expected

    def test_total_len(self, downloader):
        assert downloader.total_len == FILE_SIZE

    def test_piece_length_stored(self, downloader):
        assert downloader.piece_length == PIECE_LENGTH

    def test_peer_id_length(self, downloader):
        assert len(downloader.peer_id) == 20

    def test_peer_id_prefix(self, downloader):
        assert downloader.peer_id.startswith(b"-PY0001-")

    def test_empty_downloaded_pieces(self, downloader):
        assert downloader.downloaded_pieces == {}

    def test_empty_pieces_in_progress(self, downloader):
        assert downloader.pieces_in_progress == set()

    def test_piece_locks_count(self, downloader):
        assert len(downloader.piece_locks) == downloader.num_pieces

    def test_multi_file_torrent(self, tmp_path):
        """TorrentDownloader with a multi-file torrent dict."""
        file_data_a = b"A" * 300
        file_data_b = b"B" * 400
        combined = file_data_a + file_data_b
        hashes = _piece_hashes(combined, PIECE_LENGTH)
        info = {
            b"name": b"multi",
            b"piece length": PIECE_LENGTH,
            b"pieces": hashes,
            b"files": [
                {b"length": 300, b"path": [b"a.txt"]},
                {b"length": 400, b"path": [b"b.txt"]},
            ],
        }
        torrent = {b"announce": b"http://t.test/ann", b"info": info}
        path = tmp_path / "multi.torrent"
        path.write_bytes(find_parse(torrent))
        dl = TorrentDownloader(str(path), [])
        assert dl.total_len == 700
        assert dl.num_pieces == (700 + PIECE_LENGTH - 1) // PIECE_LENGTH


# ---------------------------------------------------------------------------
# get_peice_length()
# ---------------------------------------------------------------------------

class TestGetPieceLength:
    def test_regular_piece(self, downloader):
        # all pieces except the last have the full piece_length
        for i in range(downloader.num_pieces - 1):
            assert downloader.get_peice_length(i) == PIECE_LENGTH

    def test_last_piece_smaller(self, downloader):
        last = downloader.num_pieces - 1
        expected = FILE_SIZE - last * PIECE_LENGTH
        assert downloader.get_peice_length(last) == expected

    def test_single_piece_file(self, tmp_path):
        """A file that fits in exactly one piece."""
        data = b"x" * PIECE_LENGTH
        path = tmp_path / "one.torrent"
        path.write_bytes(_make_torrent_bytes(data, PIECE_LENGTH))
        dl = TorrentDownloader(str(path), [])
        assert dl.num_pieces == 1
        assert dl.get_peice_length(0) == PIECE_LENGTH


# ---------------------------------------------------------------------------
# get_piece_hash()
# ---------------------------------------------------------------------------

class TestGetPieceHash:
    def test_returns_20_bytes(self, downloader):
        for i in range(downloader.num_pieces):
            assert len(downloader.get_piece_hash(i)) == 20

    def test_consecutive_hashes_are_different(self, downloader, tmp_torrent):
        """Pieces built from different data should have different hashes."""
        _, file_data = tmp_torrent
        if downloader.num_pieces < 2:
            pytest.skip("Need at least 2 pieces")
        h0 = downloader.get_piece_hash(0)
        h1 = downloader.get_piece_hash(1)
        assert h0 != h1

    def test_hash_matches_expected(self, downloader, tmp_torrent):
        _, file_data = tmp_torrent
        chunk = file_data[:PIECE_LENGTH]
        expected = hashlib.sha1(chunk).digest()
        assert downloader.get_piece_hash(0) == expected

    def test_last_piece_hash(self, downloader, tmp_torrent):
        _, file_data = tmp_torrent
        last = downloader.num_pieces - 1
        chunk = file_data[last * PIECE_LENGTH :]
        expected = hashlib.sha1(chunk).digest()
        assert downloader.get_piece_hash(last) == expected


# ---------------------------------------------------------------------------
# verify_piece()
# ---------------------------------------------------------------------------

class TestVerifyPiece:
    def test_correct_piece_verifies(self, downloader, tmp_torrent):
        _, file_data = tmp_torrent
        for i in range(downloader.num_pieces):
            start = i * PIECE_LENGTH
            end = start + downloader.get_peice_length(i)
            chunk = file_data[start:end]
            assert downloader.verify_piece(i, chunk) is True

    def test_corrupted_piece_fails(self, downloader, tmp_torrent):
        _, file_data = tmp_torrent
        chunk = file_data[:PIECE_LENGTH]
        bad_chunk = bytearray(chunk)
        bad_chunk[0] ^= 0xFF          # flip one byte
        assert downloader.verify_piece(0, bytes(bad_chunk)) is False

    def test_empty_data_fails(self, downloader):
        assert downloader.verify_piece(0, b"") is False

    def test_wrong_length_fails(self, downloader, tmp_torrent):
        _, file_data = tmp_torrent
        truncated = file_data[:PIECE_LENGTH // 2]
        assert downloader.verify_piece(0, truncated) is False
