from thing import *
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
    h.drVN = b'ElmoTest'
    hf = File()
    hf.data = b'1234' * 2000
    h[b'testfile'] = hf
    ser = h.write(800*1024)
    open('/tmp/SMALL.dmg','wb').write(ser)
    os.system('open /tmp/SMALL.dmg')
    n = 10
    while 1:
        n += 1
        assert n < 20
        time.sleep(0.1)
        try:
            recovered = open('/Volumes/ElmoTest/testfile','rb').read()
        except:
            pass
        else:
            break
    os.system('umount /Volumes/ElmoTest')
    os.unlink('/tmp/SMALL.dmg')
    assert recovered == hf.data
