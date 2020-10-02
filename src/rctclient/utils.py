
# Copyright 2020, Peter Oberhofer (pob90)
# Copyright 2020, Stefan Valouch (svalouch)
# SPDX-License-Identifier: GPL-3.0-only

import struct
from datetime import datetime
from typing import Dict, Tuple, Union

from .types import DataType, EventEntry


def CRC16(data: Union[bytes, bytearray]) -> int:
    '''
    Calculates the CRC16 checksum of data. Note that this automatically skips the first byte (start token) if the
    length is uneven.
    '''
    crcsum = 0xFFFF
    polynom = 0x1021  # CCITT Polynom
    buffer = bytearray(data)

    # skip start token
    if len(data) & 0x01:
        buffer.append(0)

    for byte in buffer:
        crcsum ^= byte << 8
        for bit in range(8):
            crcsum <<= 1
            if crcsum & 0x7FFF0000:
                # ~~ overflow in bit 16
                crcsum = (crcsum & 0x0000FFFF) ^ polynom
    return crcsum


def encode_value(data_type: DataType, value: Union[bool, bytes, float, int, str]) -> bytes:
    '''
    Encodes a value suitable for transmitting as payload to the device. The actual encoding depends on the `data_type`.

    :param data_type: Data type of the `value` to be encoded. This selects the encoding mechanism.
    :param value: Data to be encoded according to the `data_type`.
    :return: The encoded value.
    :raises struct.error: If the packing failed, usually when the input value can't be encoded using the selected type.
    :raises ValueError: For string values, if the data type is not ``str`` or ``bytes``.
    '''
    if data_type == DataType.BOOL:
        if value != 0:
            value = True
        else:
            value = False
        return struct.pack('>B', value)
    elif data_type == DataType.UINT8:
        value = struct.unpack('<B', struct.pack('<b', value))[0]
        return struct.pack(">B", value)
    elif data_type == DataType.INT8:
        return struct.pack(">b", value)
    elif data_type == DataType.UINT16:
        value = struct.unpack('<H', struct.pack('<h', value))[0]
        return struct.pack(">H", value)
    elif data_type == DataType.INT16:
        return struct.pack(">h", value)
    elif data_type == DataType.UINT32:
        value = struct.unpack('<I', struct.pack('<i', value))[0]
        return struct.pack(">I", value)
    elif data_type == DataType.INT32:
        return struct.pack(">i", value)
    elif data_type == DataType.ENUM:
        value = struct.unpack('<H', struct.pack('<h', value))[0]
        return struct.pack(">H", value)
    elif data_type == DataType.FLOAT:
        return struct.pack(">f", value)
    elif data_type == DataType.STRING:
        if isinstance(value, str):
            return value.encode('utf-8')
        elif isinstance(value, bytes):
            return value
        raise ValueError(f'Invalid value of type {type(value)} for string type encoding')
        # return struct.pack("s", value)
    else:
        raise KeyError('Undefinded or unknown type')


def decode_value(data_type: DataType, data: bytes) -> Union[bool, bytes, float, int, str,
                                                            Tuple[datetime, Dict[datetime, int]],
                                                            Tuple[datetime, Dict[datetime, EventEntry]]]:
    '''
    Decodes a value received from the device.

    .. note::

       Values for a message id may be decoded using a different type than was used for encoding. For example, the
       logger history writes a unix timestamp and receives a timeseries data structure.

    :param data_type: Data type of the `value` to be decoded. This selects the decoding mechanism.
    :param value: The value to be decoded.
    :return: The decoded value, depending on the `data_type`.
    :raises struct.error: If decoding of native types failed.
    '''
    if data_type == DataType.BOOL:
        value = struct.unpack(">B", data)[0]
        if value != 0:
            return True
        else:
            return False
    elif data_type == DataType.UINT8:
        return struct.unpack(">B", data)[0]
    elif data_type == DataType.INT8:
        return struct.unpack(">b", data)[0]
    elif data_type == DataType.UINT16:
        return struct.unpack(">H", data)[0]
    elif data_type == DataType.INT16:
        return struct.unpack(">h", data)[0]
    elif data_type == DataType.UINT32:
        return struct.unpack(">I", data)[0]
    elif data_type == DataType.INT32:
        return struct.unpack(">i", data)[0]
    elif data_type == DataType.ENUM:
        return struct.unpack(">H", data)[0]
    elif data_type == DataType.FLOAT:
        return struct.unpack(">f", data)[0]
    elif data_type == DataType.STRING:
        return data.decode('utf-8')
    elif data_type == DataType.TIMESERIES:
        ts = datetime.fromtimestamp(struct.unpack('>I', data[0:4])[0])
        tsval: Dict[datetime, int] = dict()
        assert len(data) % 4 == 0, 'Data should be divisible by 4'
        assert int(len(data) / 4 % 2) == 1, 'Data should be an even number of 4-byte pairs plus the starting timestamp'
        for pair in range(0, int(len(data) / 4 - 1), 2):
            pair_ts = datetime.fromtimestamp(struct.unpack('>I', data[4 + pair * 4:4 + pair * 4 + 4])[0])
            pair_val = struct.unpack('>f', data[4 + pair * 4 + 4:4 + pair * 4 + 4 + 4])[0]
            tsval[pair_ts] = pair_val
        return ts, tsval
    elif data_type == DataType.EVENT_TABLE:
        ts = datetime.fromtimestamp(struct.unpack('>I', data[0:4])[0])
        tabval: Dict[datetime, EventEntry] = dict()
        assert len(data) % 4 == 0
        assert (len(data) - 4) % 20 == 0
        for pair in range(0, int(len(data) / 4 - 1), 5):
            entry_type = bytes([struct.unpack('>I', data[4 + pair * 4:4 + pair * 4 + 4])[0]]).decode('ascii')
            timestamp = datetime.fromtimestamp(struct.unpack('>I', data[4 + pair * 4 + 4:4 + pair * 4 + 8])[0])
            if entry_type in ['s', 'w']:
                message_id = struct.unpack('>I', data[4 + pair * 4 + 8:4 + pair * 4 + 12])[0]
                value_old = struct.unpack('>I', data[4 + pair * 4 + 12:4 + pair * 4 + 16])[0]
                value_new = struct.unpack('>I', data[4 + pair * 4 + 16:4 + pair * 4 + 20])[0]
                tabval[timestamp] = EventEntry(timestamp=timestamp, message_id=message_id, entry_type=entry_type,
                                               value_old=value_old, value_new=value_new)
            else:
                timestamp_end = datetime.fromtimestamp(
                    struct.unpack('>I', data[4 + pair * 4 + 12:4 + pair * 4 + 16])[0])
                message_id = struct.unpack('>I', data[4 + pair * 4 + 16:4 + pair * 4 + 20])[0]
                tabval[timestamp] = EventEntry(timestamp=timestamp, message_id=message_id, entry_type=entry_type,
                                               timestamp_end=timestamp_end)
        return ts, tabval
    else:
        raise KeyError('Undefined or unknown type')