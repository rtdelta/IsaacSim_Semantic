"""Independently read this capture's uncompressed MCAP data records and CRCs.

Only the subset present in this capture is accepted. Unsupported compression or
attachments fail instead of silently discarding content.
"""
import hashlib
import struct
import zlib

MAGIC = b'\x89MCAP0\r\n'


def take_string(data, offset):
    length = struct.unpack_from('<I', data, offset)[0]
    start = offset + 4
    end = start + length
    assert end <= len(data)
    return bytes(data[start:end]), end


def records(stream, end=None):
    while end is None or stream.tell() < end:
        header = stream.read(9)
        if not header:
            return
        assert len(header) == 9
        opcode, size = struct.unpack('<BQ', header)
        assert size < 256 * 1024 ** 2, 'Unexpected large MCAP record'
        if end is not None:
            assert stream.tell() + size <= end
        body = stream.read(size)
        assert len(body) == size
        yield opcode, body


def messages(path):
    import io
    schemas, channels = {}, {}
    data_end = False
    with path.open('rb') as stream:
        assert stream.read(8) == MAGIC
        stream.seek(-8, 2)
        assert stream.read(8) == MAGIC
        stream.seek(8)

        def decode(opcode, body):
            if opcode == 3:
                identifier = struct.unpack_from('<H', body)[0]
                name, offset = take_string(body, 2)
                encoding, offset = take_string(body, offset)
                definition, offset = take_string(body, offset)
                assert offset == len(body)
                value = (name, encoding, definition)
                assert identifier not in schemas or schemas[identifier] == value
                schemas[identifier] = value
            elif opcode == 4:
                identifier, schema_id = struct.unpack_from('<HH', body)
                topic, offset = take_string(body, 4)
                encoding, offset = take_string(body, offset)
                metadata_length = struct.unpack_from('<I', body, offset)[0]
                metadata = body[offset + 4:]
                assert len(metadata) == metadata_length
                value = (topic.decode(), encoding, metadata, schemas[schema_id])
                assert identifier not in channels or channels[identifier] == value
                channels[identifier] = value
            elif opcode == 5:
                channel_id, sequence, log_time, publish_time = struct.unpack_from('<HIQQ', body)
                assert len(body) >= 22
                return channels[channel_id], sequence, log_time, publish_time, body[22:]
            elif opcode not in (7,):
                raise ValueError('Unexpected nested MCAP opcode: ' + str(opcode))
            return None

        for opcode, body in records(stream):
            if opcode == 15:
                assert len(body) == 4
                data_end = True
                break
            if opcode == 6:
                assert len(body) >= 40
                start, stop, unpacked_size, crc = struct.unpack_from('<QQQI', body)
                compression, offset = take_string(body, 28)
                assert compression == b'', 'Compressed chunk needs an installed official reader'
                packed_size = struct.unpack_from('<Q', body, offset)[0]
                chunk = memoryview(body)[offset + 8:]
                assert len(chunk) == packed_size == unpacked_size
                assert crc == 0 or zlib.crc32(chunk) == crc, 'Chunk CRC mismatch'
                nested = io.BytesIO(chunk)
                for inner_opcode, inner_body in records(nested, len(chunk)):
                    result = decode(inner_opcode, inner_body)
                    if result is not None:
                        assert start <= result[2] <= stop
                        yield result
            elif opcode in (3, 4, 5):
                result = decode(opcode, body)
                if result is not None:
                    yield result
            elif opcode not in (1, 7, 8, 12, 13):
                raise ValueError('Unsupported data-section MCAP opcode: ' + str(opcode))
        assert data_end, 'Missing MCAP data-end record'


def update_ros_digest(digest, topic, timestamp, payload):
    name = topic.encode()
    digest.update(struct.pack('<I', len(name)))
    digest.update(name)
    digest.update(struct.pack('<QQ', timestamp, len(payload)))
    digest.update(payload)


def file_digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(4 * 1024 ** 2):
            digest.update(block)
    return digest.hexdigest()
