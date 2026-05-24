"""
Tests for BittorrentPeer class in BittorrentPeer.py.

Network I/O is replaced by AsyncMock / MagicMock so no real sockets are
opened during the test run.
"""
import asyncio
import struct
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from BittorrentPeer import BittorrentPeer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_peer(**kwargs):
    """Return a BittorrentPeer with sensible defaults."""
    defaults = dict(ip="127.0.0.1", port=6881, info_hash=b"A" * 20, peer_id=b"B" * 20)
    defaults.update(kwargs)
    return BittorrentPeer(**defaults)


def _attach_mock_io(peer):
    """Attach mock reader/writer to *peer* so message-level tests work."""
    peer.reader = AsyncMock()
    peer.writer = MagicMock()
    peer.writer.drain = AsyncMock()
    peer.writer.close = MagicMock()
    peer.writer.wait_closed = AsyncMock()
    return peer


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestBittorrentPeerInit:
    def test_default_attributes(self):
        peer = make_peer()
        assert peer.ip == "127.0.0.1"
        assert peer.port == 6881
        assert peer.info_hash == b"A" * 20
        assert peer.peer_id == b"B" * 20
        assert peer.timeout == 10

    def test_initial_state(self):
        peer = make_peer()
        assert peer.peer_choking is True
        assert peer.peer_interested is False
        assert peer.choked is False
        assert peer.interested is False
        assert peer.bitfield is None
        assert peer.reader is None
        assert peer.writer is None

    def test_custom_timeout(self):
        peer = make_peer(timeout=30)
        assert peer.timeout == 30


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------

class TestConnect:
    @pytest.mark.asyncio
    async def test_successful_connection(self):
        peer = make_peer()
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            result = await peer.connect()
        assert result is True
        assert peer.reader is mock_reader
        assert peer.writer is mock_writer

    @pytest.mark.asyncio
    async def test_failed_connection_returns_false(self):
        peer = make_peer()
        with patch("asyncio.open_connection", side_effect=ConnectionRefusedError("refused")):
            result = await peer.connect()
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self):
        peer = make_peer(timeout=1)
        with patch("asyncio.open_connection", side_effect=asyncio.TimeoutError()):
            result = await peer.connect()
        assert result is False


# ---------------------------------------------------------------------------
# handshake()
# ---------------------------------------------------------------------------

def _build_handshake_response(info_hash, peer_id=b"C" * 20):
    """Build a valid 68-byte BitTorrent handshake response."""
    pstr = b"Bittorrent protocol"
    reserved = b"\x00" * 8
    return struct.pack("B", len(pstr)) + pstr + reserved + info_hash + peer_id


class TestHandshake:
    @pytest.mark.asyncio
    async def test_valid_handshake_returns_true(self):
        peer = make_peer()
        _attach_mock_io(peer)
        peer.reader.readexactly = AsyncMock(
            return_value=_build_handshake_response(peer.info_hash)
        )
        result = await peer.handshake()
        assert result is True

    @pytest.mark.asyncio
    async def test_sends_correct_handshake_bytes(self):
        peer = make_peer()
        _attach_mock_io(peer)
        peer.reader.readexactly = AsyncMock(
            return_value=_build_handshake_response(peer.info_hash)
        )
        await peer.handshake()
        written = peer.writer.write.call_args[0][0]
        pstr = b"BitTorrent protocol"
        assert written[0] == len(pstr)
        assert written[1 : 1 + len(pstr)] == pstr
        assert written[28:48] == peer.info_hash
        assert written[48:68] == peer.peer_id

    @pytest.mark.asyncio
    async def test_handshake_exception_returns_false(self):
        peer = make_peer()
        _attach_mock_io(peer)
        peer.reader.readexactly = AsyncMock(side_effect=asyncio.TimeoutError())
        result = await peer.handshake()
        assert result is False


# ---------------------------------------------------------------------------
# send_interested()
# ---------------------------------------------------------------------------

class TestSendInterested:
    @pytest.mark.asyncio
    async def test_sets_interested_flag(self):
        peer = make_peer()
        _attach_mock_io(peer)
        assert peer.interested is False
        await peer.send_interested()
        assert peer.interested is True

    @pytest.mark.asyncio
    async def test_writes_correct_message(self):
        peer = make_peer()
        _attach_mock_io(peer)
        await peer.send_interested()
        written = peer.writer.write.call_args[0][0]
        # Message: length=1, id=2
        assert written == struct.pack(">IB", 1, 2)


# ---------------------------------------------------------------------------
# send_request()
# ---------------------------------------------------------------------------

class TestSendRequest:
    @pytest.mark.asyncio
    async def test_writes_request_message(self):
        peer = make_peer()
        _attach_mock_io(peer)
        await peer.send_request(piece_index=3, begin=0, length=16384)
        written = peer.writer.write.call_args[0][0]
        # length=13, id=6, index=3, begin=0, length=16384
        assert written == struct.pack(">IBIII", 13, 6, 3, 0, 16384)

    @pytest.mark.asyncio
    async def test_writes_request_with_offset(self):
        peer = make_peer()
        _attach_mock_io(peer)
        await peer.send_request(piece_index=0, begin=16384, length=8192)
        written = peer.writer.write.call_args[0][0]
        assert written == struct.pack(">IBIII", 13, 6, 0, 16384, 8192)


# ---------------------------------------------------------------------------
# receive_message()
# ---------------------------------------------------------------------------

class TestReceiveMessage:
    @pytest.mark.asyncio
    async def test_receive_keepalive_returns_none(self):
        peer = make_peer()
        _attach_mock_io(peer)
        # length = 0 → keep-alive
        peer.reader.readexactly = AsyncMock(return_value=struct.pack(">I", 0))
        msg_id, payload = await peer.receive_message()
        assert msg_id is None
        assert payload is None

    @pytest.mark.asyncio
    async def test_receive_unchoke(self):
        peer = make_peer()
        _attach_mock_io(peer)
        length_bytes = struct.pack(">I", 1)
        msg_bytes = bytes([1])  # id=1 unchoke
        peer.reader.readexactly = AsyncMock(side_effect=[length_bytes, msg_bytes])
        msg_id, payload = await peer.receive_message()
        assert msg_id == 1
        assert payload == b""

    @pytest.mark.asyncio
    async def test_receive_bitfield(self):
        peer = make_peer()
        _attach_mock_io(peer)
        bitfield = b"\xff\x80"
        length_bytes = struct.pack(">I", 1 + len(bitfield))
        msg_bytes = bytes([5]) + bitfield  # id=5 bitfield
        peer.reader.readexactly = AsyncMock(side_effect=[length_bytes, msg_bytes])
        msg_id, payload = await peer.receive_message()
        assert msg_id == 5
        assert payload == bitfield

    @pytest.mark.asyncio
    async def test_receive_timeout_returns_none(self):
        peer = make_peer()
        _attach_mock_io(peer)
        peer.reader.readexactly = AsyncMock(side_effect=asyncio.TimeoutError())
        msg_id, payload = await peer.receive_message()
        assert msg_id is None
        assert payload is None

    @pytest.mark.asyncio
    async def test_receive_exception_returns_none(self):
        peer = make_peer()
        _attach_mock_io(peer)
        peer.reader.readexactly = AsyncMock(side_effect=ConnectionResetError())
        msg_id, payload = await peer.receive_message()
        assert msg_id is None
        assert payload is None


# ---------------------------------------------------------------------------
# handel_message()
# ---------------------------------------------------------------------------

class TestHandelMessage:
    @pytest.mark.asyncio
    async def test_none_msg_id_returns_none(self):
        peer = make_peer()
        result = await peer.handel_message(None, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_choke_sets_flag(self):
        peer = make_peer()
        peer.peer_choking = False
        await peer.handel_message(0, b"")
        assert peer.peer_choking is True

    @pytest.mark.asyncio
    async def test_unchoke_clears_flag(self):
        peer = make_peer()
        peer.peer_choking = True
        _attach_mock_io(peer)  # needed for print (no-op here)
        await peer.handel_message(1, b"")
        assert peer.peer_choking is False

    @pytest.mark.asyncio
    async def test_interested_sets_flag(self):
        peer = make_peer()
        await peer.handel_message(2, b"")
        assert peer.peer_interested is True

    @pytest.mark.asyncio
    async def test_not_interested_clears_flag(self):
        peer = make_peer()
        peer.peer_interested = True
        await peer.handel_message(3, b"")
        assert peer.peer_interested is False

    @pytest.mark.asyncio
    async def test_bitfield_stores_payload(self):
        peer = make_peer()
        _attach_mock_io(peer)
        bitfield = b"\xf0\x0f"
        await peer.handel_message(5, bitfield)
        assert peer.bitfield == bitfield

    @pytest.mark.asyncio
    async def test_piece_message_returns_tuple(self):
        peer = make_peer()
        block = b"data" * 16
        payload = struct.pack(">II", 2, 512) + block
        result = await peer.handel_message(7, payload)
        assert result == ("piece", 2, 512, block)

    @pytest.mark.asyncio
    async def test_piece_message_index_zero(self):
        peer = make_peer()
        payload = struct.pack(">II", 0, 0) + b"blockdata"
        result = await peer.handel_message(7, payload)
        assert result == ("piece", 0, 0, b"blockdata")

    @pytest.mark.asyncio
    async def test_unknown_message_returns_none(self):
        peer = make_peer()
        result = await peer.handel_message(99, b"")
        assert result is None


# ---------------------------------------------------------------------------
# has_piece()
# ---------------------------------------------------------------------------

class TestHasPiece:
    @pytest.mark.asyncio
    async def test_no_bitfield_returns_false(self):
        peer = make_peer()
        assert await peer.has_piece(0) is False

    @pytest.mark.asyncio
    async def test_first_piece_set(self):
        peer = make_peer()
        peer.bitfield = b"\x80"  # bit 7 of byte 0 → piece 0
        assert await peer.has_piece(0) is True

    @pytest.mark.asyncio
    async def test_first_piece_not_set(self):
        peer = make_peer()
        peer.bitfield = b"\x7f"  # bit 7 of byte 0 is 0 → piece 0 absent
        assert await peer.has_piece(0) is False

    @pytest.mark.asyncio
    async def test_all_pieces_set(self):
        peer = make_peer()
        peer.bitfield = b"\xff\xff"
        for i in range(16):
            assert await peer.has_piece(i) is True

    @pytest.mark.asyncio
    async def test_no_pieces_set(self):
        peer = make_peer()
        peer.bitfield = b"\x00\x00"
        for i in range(16):
            assert await peer.has_piece(i) is False

    @pytest.mark.asyncio
    async def test_second_byte_first_bit(self):
        peer = make_peer()
        peer.bitfield = b"\x00\x80"  # piece 8 is set
        assert await peer.has_piece(8) is True
        assert await peer.has_piece(7) is False
        assert await peer.has_piece(9) is False

    @pytest.mark.asyncio
    async def test_specific_bit_pattern(self):
        # 0b10100000 = 0xa0: pieces 0 and 2 are set
        peer = make_peer()
        peer.bitfield = b"\xa0"
        assert await peer.has_piece(0) is True
        assert await peer.has_piece(1) is False
        assert await peer.has_piece(2) is True
        assert await peer.has_piece(3) is False

    @pytest.mark.asyncio
    async def test_piece_index_out_of_range(self):
        peer = make_peer()
        peer.bitfield = b"\xff"  # only covers pieces 0-7
        assert await peer.has_piece(100) is False


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------

class TestClose:
    @pytest.mark.asyncio
    async def test_close_calls_writer_close(self):
        peer = make_peer()
        _attach_mock_io(peer)
        await peer.close()
        peer.writer.close.assert_called_once()
        peer.writer.wait_closed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_without_writer_does_not_raise(self):
        peer = make_peer()
        # writer is None — should not raise
        await peer.close()
