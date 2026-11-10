import ctypes
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import sys
if os.environ.get('FCITX_PATCH1_TEST') != '1':
    environment = dict(os.environ, FCITX_PATCH1_TEST='1')
    sys.exit(subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1600x900x24',
                            'dbus-run-session', '--', sys.executable, __file__],
                           env=environment).returncode)
import dbus

task_dir = Path(tempfile.mkdtemp(prefix='fcitx5-review-isolated-'))
for name in ('home', 'config', 'data', 'cache', 'runtime'):
    (task_dir / name).mkdir(mode=0o700)
os.environ.update(HOME=str(task_dir/'home'), XDG_CONFIG_HOME=str(task_dir/'config'),
                  XDG_DATA_HOME=str(task_dir/'data'), XDG_CACHE_HOME=str(task_dir/'cache'),
                  XDG_RUNTIME_DIR=str(task_dir/'runtime'), LANG='zh_CN.UTF-8')
conf = task_dir/'config/fcitx5'
(conf/'conf').mkdir(parents=True)
(conf/'profile').write_text('[Groups/0]\nName=Review\nDefault Layout=us\nDefaultIM=rime\n\n[Groups/0/Items/0]\nName=rime\n\n[GroupOrder]\n0=Review\n')
(conf/'conf/classicui.conf').write_text('Vertical Candidate List=False\nTheme=default\nFont="Sans 12"\n')
(conf/'conf/rime.conf').write_text('PreeditMode=Raw input\nPreeditCursorPositionAtBeginning=False\n')
rime = task_dir/'data/fcitx5/rime'
rime.mkdir(parents=True)
(rime/'default.yaml').write_text('config_version: "1"\nschema_list:\n  - schema: review\n')
(rime/'review.schema.yaml').write_text('''schema:
  schema_id: review
  name: Review
  version: "1"
switches:
  - name: ascii_mode
    reset: 0
engine:
  processors: [ascii_composer, speller, selector, navigator, express_editor]
  segmentors: [ascii_segmentor, abc_segmentor, fallback_segmentor]
  translators: [echo_translator]
speller:
  alphabet: abcdefghijklmnopqrstuvwxyz
menu:
  page_size: 7
''')
log = (task_dir/'fcitx5.log').open('w')
fcitx = None
# Start after the synthetic host/compositor exists.
def start_fcitx():
    return subprocess.Popen(['fcitx5', '-D', '--disable=all', '--enable=xcb,dbus,dbusfrontend,classicui,keyboard,quickphrase,rime', '--ui=classicui'], stdout=log, stderr=log)

libx = ctypes.CDLL('libX11.so.6')
libx.XOpenDisplay.restype = ctypes.c_void_p
libx.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
libx.XDefaultRootWindow.restype = ctypes.c_ulong
libx.XSetWindowBackground.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong]
libx.XClearWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
libx.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
libx.XCreateSimpleWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_ulong]
libx.XCreateSimpleWindow.restype = ctypes.c_ulong
libx.XMapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
libx.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
libx.XMoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int]
libx.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
libx.XInternAtom.restype = ctypes.c_ulong
libx.XSetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
libx.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
libx.XGetImage.restype = ctypes.c_void_p
libx.XGetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
libx.XGetPixel.restype = ctypes.c_ulong
libx.XDestroyImage.argtypes = [ctypes.c_void_p]
display = libx.XOpenDisplay(None)
root = libx.XDefaultRootWindow(display)
host = libx.XCreateSimpleWindow(display, root, 50, 50, 600, 400, 0, 0, 0xffffff)
libx.XMapWindow(display, host)
libx.XSetInputFocus(display, host, 1, 0)
if os.environ.get('TEST_COMPOSITE'):
    libx.XSetSelectionOwner(display, libx.XInternAtom(display, b'_NET_WM_CM_S0', 0), host, 0)
libx.XSync(display, 0)
libx.XSetWindowBackground(display, root, 0x735997)
libx.XClearWindow(display, root)
libx.XSync(display, 0)

def image_pixel(window, x, y):
    img = libx.XGetImage(display, window, x, y, 1, 1, ctypes.c_ulong(-1), 2)
    if not img:
        return None
    result = libx.XGetPixel(img, 0, 0)
    libx.XDestroyImage(img)
    return hex(result)

def panel(stage):
    time.sleep(.15)
    tree = subprocess.check_output(['xwininfo', '-root', '-tree'], text=True)
    found = re.search(r'(0x[0-9a-f]+) "Fcitx5 Input Window".*', tree)
    assert found, tree
    wid = found.group(1)
    info = subprocess.check_output(['xwininfo', '-id', wid], text=True)
    fields = {}
    for k in ('Absolute upper-left X', 'Absolute upper-left Y', 'Width', 'Height', 'Depth', 'Map State'):
        fields[k] = re.search(r'\b' + re.escape(k) + r':\s+([^\n]+)', info).group(1)
    if fields['Map State'] == 'IsViewable':
        fields['right_blank_pixel'] = image_pixel(int(wid, 16), max(0, int(fields['Width'])-150), 10)
        fields['root_background_pixel'] = image_pixel(root, 10, 10)
    print(stage, fields, flush=True)
    return fields

try:
    fcitx = start_fcitx()
    bus = dbus.SessionBus()
    for i in range(80):
        if bus.name_has_owner('org.fcitx.Fcitx5'):
            break
        time.sleep(.1)
    time.sleep(1)
    im = dbus.Interface(bus.get_object('org.fcitx.Fcitx5', '/org/freedesktop/portal/inputmethod'), 'org.fcitx.Fcitx.InputMethod1')
    path, uuid = im.CreateInputContext(dbus.Array([('program', 'fcitx5-review'), ('display', 'x11:' + os.environ['DISPLAY'])], signature='(ss)'))
    ic = dbus.Interface(bus.get_object('org.fcitx.Fcitx5', path), 'org.fcitx.Fcitx.InputContext1')
    ic.SetCapability(dbus.UInt64(18))
    ic.FocusIn()
    ic.SetCursorRect(100, 100, 1, 20)
    subprocess.run(['fcitx5-remote', '-s', 'rime'], check=True)
    time.sleep(.5)
    for c in 'abc':
        print('KEY', c, bool(ic.ProcessKeyEvent(ord(c), 0, 0, False, 0)), flush=True)
        time.sleep(.1)
    before = panel('RIME_BEFORE_MOVE')
    ic.SetCursorRect(120, 100, 1, 20)
    caret = panel('RIME_CARET_MOVE')
    assert caret['Absolute upper-left X'] == before['Absolute upper-left X']
    libx.XMoveWindow(display, host, 350, 250)
    libx.XSync(display, 0)
    ic.SetCursorRect(400, 300, 1, 20)
    after = panel('RIME_AFTER_MOVE_CURSOR_RECT')
    assert int(after['Absolute upper-left X']) - int(before['Absolute upper-left X']) == 300
    assert int(after['Absolute upper-left Y']) - int(before['Absolute upper-left Y']) == 200
    if os.environ.get('TEST_COMPOSITE'):
        assert int(after['Depth']) == 32 and int(after['Width']) == 1600
        assert after['right_blank_pixel'] == '0x0'
    else:
        assert int(after['Depth']) == 24 and int(after['Width']) < 1600
    print('PASS: host movement and canvas fallback', flush=True)
    ic.ProcessKeyEvent(0xff1b, 0, 0, False, 0)
    ic.SetCursorRect(1500, 100, 1, 20)
    ic.ProcessKeyEvent(ord('a'), 0, 0, False, 0)
    narrow = panel('EDGE_NARROW')
    for _ in range(40):
        ic.ProcessKeyEvent(ord('a'), 0, 0, False, 0)
    wide = panel('EDGE_WIDE')
    for _ in range(40):
        ic.ProcessKeyEvent(0xff08, 0, 0, False, 0)
    shrunk = panel('EDGE_SHRUNK')
    assert int(wide['Absolute upper-left X']) < int(narrow['Absolute upper-left X'])
    assert shrunk['Absolute upper-left X'] == wide['Absolute upper-left X']
    print('PASS: frozen caret anchor and sticky overflow', flush=True)
    ic.ProcessKeyEvent(0xff1b, 0, 0, False, 0)
    ic.SetCursorRect(100, 100, 1, 20)
    print('QUICKPHRASE_TRIGGER', bool(ic.ProcessKeyEvent(0x60, 0, 64, False, 0)), flush=True)
    panel('QUICKPHRASE_NO_COMPOSITOR')
finally:
    fcitx.terminate()
    try:
        fcitx.wait(timeout=5)
    except subprocess.TimeoutExpired:
        fcitx.kill()
        fcitx.wait()
    print('LOG', task_dir/'fcitx5.log', flush=True)
