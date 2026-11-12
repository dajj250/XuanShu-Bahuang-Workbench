"""Local-only named-pipe server for the in-game GGBH Bridge Mod."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import queue
import secrets
import struct
import threading
import uuid

from .core import DataError

PIPE_NAME = r"\\.\pipe\GGBH.Workbench.v1"
MAX_MESSAGE = 1024 * 1024
PIPE_TYPE_BYTE = 0x00000000
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008


class LiveServer:
    def __init__(self):
        self.token = secrets.token_urlsafe(32)
        self.outgoing = queue.Queue()
        self.results = queue.Queue()
        self.connected = False
        self.detail = "等待游戏客户端连接"
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        if os.name != "nt":
            raise DataError("实时连接仅支持 Windows")
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="GGBH live server")
        self._thread.start()

    def request(self, command, payload=None):
        request_id = uuid.uuid4().hex
        self.outgoing.put({"type": command, "requestId": request_id, "protocol": 1,
                           "token": self.token, "payload": payload or {}})
        return request_id

    def poll(self):
        rows = []
        while True:
            try:
                rows.append(self.results.get_nowait())
            except queue.Empty:
                return rows

    def stop(self):
        self._stop.set()

    def _run(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                             wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                             wintypes.DWORD, ctypes.c_void_p]
        kernel.CreateNamedPipeW.restype = wintypes.HANDLE
        kernel.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        kernel.ConnectNamedPipe.restype = wintypes.BOOL
        kernel.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        kernel.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                     ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        kernel.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        invalid = ctypes.c_void_p(-1).value
        while not self._stop.is_set():
            # Windows named pipes can otherwise be reached through SMB. Explicitly reject
            # every remote machine; the per-launch random token authenticates messages.
            handle = kernel.CreateNamedPipeW(PIPE_NAME, 0x00000003,
                                             PIPE_TYPE_BYTE | PIPE_REJECT_REMOTE_CLIENTS,
                                             1, MAX_MESSAGE, MAX_MESSAGE, 0, None)
            if handle == invalid:
                self.detail = f"无法创建通信管道（Windows 错误 {ctypes.get_last_error()}）"
                return
            try:
                ok = kernel.ConnectNamedPipe(handle, None)
                if not ok and ctypes.get_last_error() != 535:  # ERROR_PIPE_CONNECTED
                    self.detail = f"客户端连接失败（Windows 错误 {ctypes.get_last_error()}）"
                    continue
                self.connected = True
                self.detail = "游戏客户端已连接"
                hello = {"type": "hello", "requestId": uuid.uuid4().hex, "protocol": 1,
                         "token": self.token, "payload": {"serverVersion": "1.1.3"}}
                self._exchange(kernel, handle, hello)
                while not self._stop.is_set():
                    try:
                        message = self.outgoing.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    self._exchange(kernel, handle, message)
            except (OSError, DataError, ValueError) as exc:
                self.detail = f"连接已断开：{exc}"
            finally:
                self.connected = False
                kernel.DisconnectNamedPipe(handle)
                kernel.CloseHandle(handle)

    def _exchange(self, kernel, handle, message):
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > MAX_MESSAGE:
            raise DataError("实时命令超过 1 MiB 上限")
        self._write(kernel, handle, struct.pack("<I", len(payload)) + payload)
        size = struct.unpack("<I", self._read(kernel, handle, 4))[0]
        if not 0 < size <= MAX_MESSAGE:
            raise DataError("客户端响应长度无效")
        response = json.loads(self._read(kernel, handle, size).decode("utf-8"))
        if not isinstance(response, dict) or response.get("requestId") != message["requestId"]:
            raise DataError("客户端响应编号不匹配")
        self.results.put(response)

    @staticmethod
    def _read(kernel, handle, count):
        chunks = bytearray()
        while len(chunks) < count:
            size = count - len(chunks)
            buffer = ctypes.create_string_buffer(size)
            read = wintypes.DWORD()
            if not kernel.ReadFile(handle, buffer, size, ctypes.byref(read), None) or not read.value:
                raise OSError(ctypes.get_last_error(), "读取命名管道失败")
            chunks.extend(buffer.raw[:read.value])
        return bytes(chunks)

    @staticmethod
    def _write(kernel, handle, data):
        offset = 0
        while offset < len(data):
            chunk = data[offset:]
            buffer = ctypes.create_string_buffer(chunk)
            written = wintypes.DWORD()
            if not kernel.WriteFile(handle, buffer, len(chunk), ctypes.byref(written), None):
                raise OSError(ctypes.get_last_error(), "写入命名管道失败")
            offset += written.value
