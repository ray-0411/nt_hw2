import struct
import json
import asyncio

MAX_LEN = 65536

async def send_msg(writer: asyncio.StreamWriter, obj: dict):
    """封裝 JSON 封包並以 Length-Prefixed 格式傳送"""
    data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
    n = len(data)
    if n > MAX_LEN:
        raise ValueError(f"封包過大: {n} bytes")
    writer.write(struct.pack('!I', n) + data)
    await writer.drain()

async def recv_msg(reader: asyncio.StreamReader):
    """接收並解析一個完整封包"""
    header = await reader.readexactly(4)
    (n,) = struct.unpack('!I', header)
    if not (0 < n <= MAX_LEN):
        raise ValueError(f"封包長度無效: {n}")
    body = await reader.readexactly(n)
    return json.loads(body.decode('utf-8'))
