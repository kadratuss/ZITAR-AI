import ctypes
from ctypes import wintypes


MUTEX_NAME = r"Local\PortfolioAI_AgentRunner"
ERROR_ALREADY_EXISTS = 183

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_CreateMutexW = _kernel32.CreateMutexW
_CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
_CreateMutexW.restype = wintypes.HANDLE

_CloseHandle = _kernel32.CloseHandle
_CloseHandle.argtypes = [wintypes.HANDLE]
_CloseHandle.restype = wintypes.BOOL


class AgentAlreadyRunning(RuntimeError):
    pass


class AgentLock:
    def __init__(self):
        self._handle = None

    def acquire(self):
        if self._handle is not None:
            return

        ctypes.set_last_error(0)
        handle = _CreateMutexW(None, False, MUTEX_NAME)

        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())

        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            _CloseHandle(handle)
            raise AgentAlreadyRunning(
                "Baska bir PortfolioAI ajani zaten calisiyor."
            )

        self._handle = handle

    def release(self):
        if self._handle is not None:
            _CloseHandle(self._handle)
            self._handle = None