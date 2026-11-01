import json

from pasr.hardware.watch.protocol import (
    BLE_CHUNK_BYTES,
    MAX_TEXT,
    LineDecoder,
    WatchReply,
    chunks,
    consent_command,
    notify_command,
    parse_reply,
    ping_command,
)


def test_commands_call_the_app_without_echo():
    assert consent_command(3, "Café?", 60.4) == b'\x10consent("3","Caf\\u00e9?",60)\n'
    assert notify_command(4, "Hi") == b'\x10notify("Hi");Bluetooth.println("NOTIFIED:4")\n'
    assert ping_command(5) == b'\x10Bluetooth.println("PONG:5:"+typeof consent)\n'
    for command in (consent_command(1, '“x” \\ "y"', 9), notify_command(1, "\n")):
        assert command.isascii() and command.count(b"\n") == 1  # one line, plain ASCII


def test_text_is_a_safe_javascript_string_and_truncated():
    data = notify_command(1, "x" * 500 + '");evil();("')
    literal = data[len(b"\x10notify(") : data.index(b");Bluetooth")]
    assert json.loads(literal) == "x" * MAX_TEXT


def test_chunks_fit_the_ble_mtu_and_reassemble():
    data = notify_command(1, "Reminder: dentist at 9")
    pieces = chunks(data)
    assert all(len(p) <= BLE_CHUNK_BYTES for p in pieces)
    assert b"".join(pieces) == data


def test_line_decoder_handles_fragments():
    decoder = LineDecoder()
    assert decoder.feed(b"CONSENT:1") == []
    assert decoder.feed(b":YES\r\n>") == ["CONSENT:1:YES"]
    assert decoder.feed(b"\n") == [">"]


def test_replies_are_parsed_and_noise_is_ignored():
    assert parse_reply("CONSENT:1:NO") == WatchReply("answer", 1, "no")
    assert parse_reply("CONSENT:7:YES\r") == WatchReply("answer", 7, "yes")
    assert parse_reply("NOTIFIED:2") == WatchReply("ack", 2)
    assert parse_reply("PONG:3:function") == WatchReply("pong", 3, "function")
    assert parse_reply("PONG:3:undefined") == WatchReply("pong", 3, "undefined")
    for noise in [">", "Uncaught Error", "CONSENT:p17:YES", "CONSENT:1:MAYBE", "NOTIFIED:x",
                  "NOTIFIED:2:extra", "PONG:3:", "OTHER:1:YES", ""]:  # fmt: skip
        assert parse_reply(noise) is None
