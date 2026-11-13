"""Real GTK/XIM client for the isolated candidate-window regression test."""
import ctypes
import json
import os
import subprocess
import time
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gtk, GdkX11, GLib, Pango

window = Gtk.Window(title='Isolated XIM baseline test')
entry = Gtk.Entry()
entry.set_property('im-module', 'xim')
entry.override_font(Pango.FontDescription('Sans 14'))
window.add(entry)
window.set_default_size(500, 1)
window.move(100, 900 - round(36 * int(os.environ.get('TEST_DPI', '96')) / 96))
window.show_all()
entry.grab_focus()

libx = ctypes.CDLL('libX11.so.6')
libx.XOpenDisplay.restype = ctypes.c_void_p
libx.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
libx.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
libx.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
libx.XKeysymToKeycode.restype = ctypes.c_uint
libxtst = ctypes.CDLL('libXtst.so.6')
libxtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
display = libx.XOpenDisplay(None)

def focus_client():
    libx.XSetInputFocus(display, window.get_window().get_xid(), 1, 0)
    libx.XSync(display, 0)
    GLib.timeout_add(500, send_key)
    return False

def send_key():
    subprocess.run(['fcitx5-remote', '-s', 'rime'], check=True)
    keycode = libx.XKeysymToKeycode(display, ord('a'))
    libxtst.XTestFakeKeyEvent(display, keycode, 1, 0)
    libxtst.XTestFakeKeyEvent(display, keycode, 0, 0)
    libx.XSync(display, 0)
    return False

deadline = time.monotonic() + 7
def report_preedit():
    if entry.get_layout().get_text() != 'a' or entry.get_text() != '':
        if time.monotonic() < deadline:
            return True
        print(json.dumps({'error': 'No active raw-letter preedit'}), flush=True)
        return False
    origin_y = window.get_window().get_origin()[-1]
    widget_y = entry.translate_coordinates(window, 0, 0)[-1]
    layout_y = entry.get_layout_offsets()[1]
    print(json.dumps({'top': origin_y + widget_y + layout_y,
                      'height': entry.get_layout().get_pixel_size()[1]}), flush=True)
    return False

GLib.timeout_add(500, focus_client)
GLib.timeout_add(250, report_preedit)
Gtk.main()
