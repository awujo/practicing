"""Wire format of the cTrader Open API (protobuf over TLS).

Each frame = 4-byte big-endian length + serialized ProtoMessage{payloadType, payload, clientMsgId}.
The message classes come from Spotware's generated *_pb2 modules vendored in ctrader/messages.
"""
import struct

from ctrader.messages import (  # noqa: F401 - model/common_model re-exported
    OpenApiCommonMessages_pb2 as common,
    OpenApiCommonModelMessages_pb2 as common_model,
    OpenApiMessages_pb2 as oa,
    OpenApiModelMessages_pb2 as model,
)

ProtoMessage = common.ProtoMessage
MAX_FRAME = 64 * 1024 * 1024


def _build_registry():
    reg = {}
    for mod in (common, oa):
        for name, desc in mod.DESCRIPTOR.message_types_by_name.items():
            f = desc.fields_by_name.get("payloadType")
            if f is None or name == "ProtoMessage":
                continue
            reg[f.default_value] = getattr(mod, name)
    return reg


REGISTRY = _build_registry()  # payloadType (int) -> message class


def payload_type(msg):
    return msg.DESCRIPTOR.fields_by_name["payloadType"].default_value


def encode(msg, client_msg_id=None):
    """Wrap a typed message in ProtoMessage and length-prefix it."""
    wrapper = ProtoMessage(payloadType=payload_type(msg), payload=msg.SerializeToString())
    if client_msg_id:
        wrapper.clientMsgId = str(client_msg_id)
    body = wrapper.SerializeToString()
    return struct.pack(">I", len(body)) + body


def decode_body(body):
    """bytes of one ProtoMessage -> (typed message or None, payloadType, clientMsgId)."""
    wrapper = ProtoMessage()
    wrapper.ParseFromString(body)
    cls = REGISTRY.get(wrapper.payloadType)
    msg = None
    if cls is not None:
        msg = cls()
        msg.ParseFromString(wrapper.payload)
    cid = wrapper.clientMsgId if wrapper.HasField("clientMsgId") else None
    return msg, wrapper.payloadType, cid


def split_frames(buf):
    """Split a byte buffer into complete frame bodies. Returns (bodies, remaining_bytes)."""
    bodies = []
    while len(buf) >= 4:
        (n,) = struct.unpack(">I", buf[:4])
        if n > MAX_FRAME:
            raise ValueError(f"frame too large: {n}")
        if len(buf) < 4 + n:
            break
        bodies.append(bytes(buf[4:4 + n]))
        buf = buf[4 + n:]
    return bodies, buf


def read_frame(sock):
    """Blocking read of one frame body from a socket-like object (recv)."""
    head = _recv_exact(sock, 4)
    (n,) = struct.unpack(">I", head)
    if n > MAX_FRAME:
        raise ValueError(f"frame too large: {n}")
    return _recv_exact(sock, n)


def _recv_exact(sock, n):
    chunks, got = [], 0
    while got < n:
        b = sock.recv(n - got)
        if not b:
            raise ConnectionError("connection closed by server")
        chunks.append(b)
        got += len(b)
    return b"".join(chunks)
