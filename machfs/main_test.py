from main import *
import os
import time

def test_roundtrip():
    h = Volume()
    f = File()
    h[b'single file'] = f
    f.data = f.rsrc = b'1234' * 4096

    copies = [h.write(800*1024)]
    for i in range(2):
        h2 = Volume()
        h2.read(copies[-1])
        copies.append(h2.write(800*1024))

    assert copies[0] == copies[1]
    assert copies[1] == copies[2]

def test_macos_mount():
    h = Volume()
    h.name = b'ElmoTest'
    hf = File()
    hf.data = b'12345' * 10
    for i in reversed(range(100)):
        last = b'testfile-%03d' % i
        h[last] = hf
    ser = h.write(10*1024*1024)

    h2 = Volume()
    h2.read(ser)
    assert h2[b'testfile-000'].data == hf.data

    open('/tmp/SMALL.dmg','wb').write(ser)
    os.system('hdiutil attach /tmp/SMALL.dmg')
    n = 10
    while 1:
        n += 1
        assert n < 200
        time.sleep(0.1)
        try:
            os.stat('/Volumes/ElmoTest/testfile-000')
        except:
            pass
        else:
            break
    recovered = open('/Volumes/ElmoTest/' + last.decode('ascii'),'rb').read()
    os.system('umount /Volumes/ElmoTest')
    assert recovered == hf.data
