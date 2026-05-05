"""
Tests for parser.py — bencode encode/decode functions.
"""
import pytest
from parser import (
    bdncode_to_dict,
    dict_to_bdncode_dict_,
    str_to_bencode,
    byte_to_bencode,
    find_parse,
    decode_peers,
)


# ---------------------------------------------------------------------------
# bdncode_to_dict
# ---------------------------------------------------------------------------

class TestBdncodeToDict:
    """Tests for the bencode decoder."""

    def test_parse_positive_integer(self):
        assert bdncode_to_dict(b"i42e") == 42

    def test_parse_zero(self):
        assert bdncode_to_dict(b"i0e") == 0

    def test_parse_negative_integer(self):
        assert bdncode_to_dict(b"i-5e") == -5

    def test_parse_large_integer(self):
        assert bdncode_to_dict(b"i1000000000e") == 1_000_000_000

    def test_parse_bytestring(self):
        assert bdncode_to_dict(b"4:spam") == b"spam"

    def test_parse_empty_bytestring(self):
        assert bdncode_to_dict(b"0:") == b""

    def test_parse_single_char_bytestring(self):
        assert bdncode_to_dict(b"1:x") == b"x"

    def test_parse_bytestring_with_special_chars(self):
        assert bdncode_to_dict(b"5:hello") == b"hello"

    def test_parse_empty_list(self):
        assert bdncode_to_dict(b"le") == []

    def test_parse_list_of_strings(self):
        assert bdncode_to_dict(b"l4:spam3:fooe") == [b"spam", b"foo"]

    def test_parse_list_of_ints(self):
        assert bdncode_to_dict(b"li1ei2ei3ee") == [1, 2, 3]

    def test_parse_mixed_list(self):
        assert bdncode_to_dict(b"l4:spami42ee") == [b"spam", 42]

    def test_parse_empty_dict(self):
        assert bdncode_to_dict(b"de") == {}

    def test_parse_simple_dict(self):
        result = bdncode_to_dict(b"d3:cow3:moo4:spam4:eggse")
        assert result == {b"cow": b"moo", b"spam": b"eggs"}

    def test_parse_dict_with_int_value(self):
        result = bdncode_to_dict(b"d3:numi99ee")
        assert result == {b"num": 99}

    def test_parse_nested_dict(self):
        result = bdncode_to_dict(b"d4:infod4:name4:testee")
        assert result == {b"info": {b"name": b"test"}}

    def test_parse_dict_with_list_value(self):
        result = bdncode_to_dict(b"d5:itemsli1ei2eee")
        assert result == {b"items": [1, 2]}

    def test_parse_list_containing_dict(self):
        result = bdncode_to_dict(b"ld3:key5:valueee")
        assert result == [{b"key": b"value"}]

    def test_torrent_like_structure(self):
        """Simulate a minimal torrent info-dict (generated via find_parse for correct encoding)."""
        torrent = {
            b"announce": b"http://tracker.test/ann",
            b"info": {b"length": 100, b"name": b"test"},
        }
        data = find_parse(torrent)
        result = bdncode_to_dict(data)
        assert result[b"announce"] == b"http://tracker.test/ann"
        assert result[b"info"][b"length"] == 100
        assert result[b"info"][b"name"] == b"test"

    def test_invalid_type_raises(self):
        with pytest.raises((ValueError, Exception)):
            bdncode_to_dict(b"x")


# ---------------------------------------------------------------------------
# str_to_bencode
# ---------------------------------------------------------------------------

class TestStrToBencode:
    """Tests for the bytes → bencode-string encoder."""

    def test_basic_bytes(self):
        assert str_to_bencode(b"hello") == b"5:hello"

    def test_empty_bytes(self):
        assert str_to_bencode(b"") == b"0:"

    def test_single_byte(self):
        assert str_to_bencode(b"a") == b"1:a"

    def test_binary_bytes(self):
        payload = bytes(range(8))
        result = str_to_bencode(payload)
        assert result == b"8:" + payload


# ---------------------------------------------------------------------------
# byte_to_bencode
# ---------------------------------------------------------------------------

class TestByteToBencode:
    """Tests for the integer → bencode-int encoder."""

    def test_positive(self):
        assert byte_to_bencode(42) == b"i42e"

    def test_zero(self):
        assert byte_to_bencode(0) == b"i0e"

    def test_negative(self):
        assert byte_to_bencode(-5) == b"i-5e"

    def test_large_value(self):
        assert byte_to_bencode(999999) == b"i999999e"


# ---------------------------------------------------------------------------
# find_parse
# ---------------------------------------------------------------------------

class TestFindParse:
    """Tests for the type-dispatch encoder."""

    def test_str_type(self):
        assert find_parse("hello") == b"5:hello"

    def test_bytes_type(self):
        assert find_parse(b"hello") == b"5:hello"

    def test_int_type(self):
        assert find_parse(42) == b"i42e"

    def test_int_zero(self):
        assert find_parse(0) == b"i0e"

    def test_list_of_bytes(self):
        assert find_parse([b"a", b"bb"]) == b"l1:a2:bbe"

    def test_list_of_ints(self):
        assert find_parse([1, 2]) == b"li1ei2ee"

    def test_empty_list(self):
        assert find_parse([]) == b"le"

    def test_dict_type(self):
        assert find_parse({b"k": b"v"}) == b"d1:k1:ve"

    def test_nested_dict(self):
        result = find_parse({b"a": {b"b": 1}})
        assert result == b"d1:ad1:bi1eee"

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError):
            find_parse(1.5)

    def test_invalid_none_raises(self):
        with pytest.raises((ValueError, TypeError)):
            find_parse(None)


# ---------------------------------------------------------------------------
# dict_to_bdncode_dict_
# ---------------------------------------------------------------------------

class TestDictToBdncodeDictUnderscored:
    """Tests for the dict → bencode-dict encoder."""

    def test_simple_bytes_values(self):
        result = dict_to_bdncode_dict_({b"key": b"value"})
        assert result == b"d3:key5:valuee"

    def test_int_value(self):
        result = dict_to_bdncode_dict_({b"num": 42})
        assert result == b"d3:numi42ee"

    def test_list_value(self):
        result = dict_to_bdncode_dict_({b"lst": [b"x"]})
        assert result == b"d3:lstl1:xee"

    def test_nested_dict_value(self):
        inner = {b"k": b"v"}
        result = dict_to_bdncode_dict_({b"d": inner})
        assert result == b"d1:dd1:k1:vee"

    def test_decode_roundtrip_simple(self):
        original = {b"name": b"test", b"size": 1000}
        encoded = dict_to_bdncode_dict_(original)
        decoded = bdncode_to_dict(encoded)
        assert decoded == original

    def test_decode_roundtrip_nested(self):
        original = {b"info": {b"length": 500, b"name": b"file.txt"}}
        encoded = dict_to_bdncode_dict_(original)
        decoded = bdncode_to_dict(encoded)
        assert decoded == original

    def test_decode_roundtrip_with_list(self):
        original = {b"pieces": [b"hash1", b"hash2"]}
        encoded = dict_to_bdncode_dict_(original)
        decoded = bdncode_to_dict(encoded)
        assert decoded == original


# ---------------------------------------------------------------------------
# decode_peers (stub)
# ---------------------------------------------------------------------------

class TestDecodePeers:
    """decode_peers is a stub that currently always returns None."""

    def test_returns_none(self):
        assert decode_peers(b"") is None

    def test_returns_none_for_any_input(self):
        assert decode_peers(b"\xc0\xa8\x01\x01\x1a\xe1") is None
