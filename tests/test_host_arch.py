import ctypes
from pathlib import Path
import sys
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import base


class HostArchTest(unittest.TestCase):
    def test_windows_uses_native_machine_not_process_machine(self):
        for process_machine, native_machine, expected in (
            (0x8664, 0xAA64, 'ARM64'),
            (0x014C, 0xAA64, 'ARM64'),
            (0, 0xAA64, 'ARM64'),
            (0x014C, 0x8664, 'AMD64'),
            (0, 0x8664, 'AMD64'),
            (0, 0x014C, 'x86'),
        ):
            with self.subTest(process_machine=process_machine, native_machine=native_machine):
                kernel32 = mock.Mock()

                def query_architecture(process, process_pointer, native_pointer):
                    self.assertEqual(process, kernel32.GetCurrentProcess.return_value)
                    ctypes.cast(process_pointer, ctypes.POINTER(base.wintypes.USHORT)).contents.value = process_machine
                    ctypes.cast(native_pointer, ctypes.POINTER(base.wintypes.USHORT)).contents.value = native_machine
                    return 1

                kernel32.IsWow64Process2.side_effect = query_architecture
                with (
                    mock.patch.object(base.sys, 'platform', 'win32'),
                    mock.patch.object(base.ctypes, 'WinDLL', return_value=kernel32, create=True),
                    mock.patch.dict(base.os.environ, {'PROCESSOR_ARCHITECTURE': 'AMD64'}, clear=True),
                    mock.patch.object(base.platform, 'machine', return_value='AMD64') as machine,
                ):
                    self.assertEqual(base._get_host_arch(), expected)
                    kernel32.IsWow64Process2.assert_called_once()
                    machine.assert_not_called()

    def test_windows_fallback_when_native_query_is_unavailable(self):
        for environment, expected in (
            ({'PROCESSOR_ARCHITEW6432': 'ARM64', 'PROCESSOR_ARCHITECTURE': 'AMD64'}, 'ARM64'),
            ({'PROCESSOR_ARCHITEW6432': 'AMD64', 'PROCESSOR_ARCHITECTURE': 'x86'}, 'AMD64'),
            ({'PROCESSOR_ARCHITECTURE': 'ARM64'}, 'ARM64'),
            ({}, 'AMD64'),
        ):
            with (
                self.subTest(environment=environment),
                mock.patch.object(base.sys, 'platform', 'win32'),
                mock.patch.object(base.ctypes, 'WinDLL', side_effect=AttributeError, create=True),
                mock.patch.dict(base.os.environ, environment, clear=True),
                mock.patch.object(base.platform, 'machine', return_value='AMD64'),
            ):
                self.assertEqual(base._get_host_arch(), expected)

    def test_windows_fallback_when_native_query_fails_or_returns_unknown_machine(self):
        for result in (0, 1, OSError('Native query failed')):
            kernel32 = mock.Mock()
            if isinstance(result, OSError):
                kernel32.IsWow64Process2.side_effect = result
            else:
                kernel32.IsWow64Process2.return_value = result
            with (
                self.subTest(result=result),
                mock.patch.object(base.sys, 'platform', 'win32'),
                mock.patch.object(base.ctypes, 'WinDLL', return_value=kernel32, create=True),
                mock.patch.dict(base.os.environ, {'PROCESSOR_ARCHITECTURE': 'ARM64'}, clear=True),
            ):
                self.assertEqual(base._get_host_arch(), 'ARM64')

    def test_non_windows_keeps_platform_detection(self):
        for host_os, expected in (('linux', 'aarch64'), ('linux', 'x86_64'), ('darwin', 'arm64')):
            with (
                self.subTest(host_os=host_os, expected=expected),
                mock.patch.object(base.sys, 'platform', host_os),
                mock.patch.object(base.ctypes, 'WinDLL', create=True) as windll,
                mock.patch.object(base.platform, 'machine', return_value=expected),
            ):
                self.assertEqual(base._get_host_arch(), expected)
                windll.assert_not_called()


if __name__ == '__main__':
    unittest.main()