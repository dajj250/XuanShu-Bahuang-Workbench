"""Read-only detection of the original server's named shared-memory channel.

Evidence: HTScript.ModMain.WriteVerData uses BinaryWriter.Write(string).
Never creates channels, sends commands, or modifies the game.
"""
import ctypes
from ctypes import wintypes
import json
import os

from .core import DataError


def unpack_string(data: bytes, maximum=256):
    length = 0
    for i in range(5):
        if i >= len(data):
            raise DataError("共享内存消息长度不完整")
        byte = data[i]
        if i == 4 and byte > 7:
            raise DataError("共享内存长度编码无效")
        length |= (byte & 127) << (7 * i)
        if not byte & 128:
            start = i + 1
            if length > maximum or start + length > len(data):
                raise DataError("共享内存消息超出边界")
            try:
                return data[start:start + length].decode("utf-8")
            except UnicodeError as exc:
                raise DataError("共享内存消息编码无效") from exc
    raise DataError("共享内存长度编码无效")


def server_version():
    if os.name != "nt":
        return {"connected": False, "detail": "共享内存检测仅支持 Windows"}
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenFileMappingW.restype = wintypes.HANDLE
    kernel.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
    kernel.MapViewOfFile.restype = ctypes.c_void_p
    kernel.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenFileMappingW(4, False, "GuiGuVer")
    if not handle:
        error = ctypes.get_last_error()
        detail = "未发现 GGBH 通信通道：游戏未运行或服务端未加载" if error == 2 else f"无法读取 GGBH 通信通道（Windows 错误 {error}）"
        return {"connected": False, "detail": detail}
    view = None
    try:
        view = kernel.MapViewOfFile(handle, 4, 0, 0, 256)
        if not view:
            return {"connected": False, "detail": "无法读取服务端版本区域"}
        payload = unpack_string(ctypes.string_at(view, 256))
        try:
            data = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise DataError("服务端版本消息不是有效 JSON") from exc
        version = data.get("ServerVersion") if isinstance(data, dict) else None
        if not isinstance(version, str) or not version:
            raise DataError("服务端没有返回可识别的版本")
        return {"connected": True, "version": version, "detail": f"检测到 GGBH 服务端 {version}，只读检测成功"}
    finally:
        if view:
            kernel.UnmapViewOfFile(view)
        kernel.CloseHandle(handle)
