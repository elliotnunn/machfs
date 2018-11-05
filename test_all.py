from machfs import *
import os
import time

def test_upperlower():
    h = Volume()
    h['alpha'] = File()
    assert h['alpha'] is h['ALPHA']
    assert list(h.keys()) == ['alpha']

def test_roundtrip():
    h = Volume()
    f = File()
    h['single file'] = f
    f.data = f.rsrc = b'1234' * 4096

    copies = [h.write(800*1024)]
    for i in range(2):
        h2 = Volume()
        h2.read(copies[-1])
        copies.append(h2.write(800*1024))

    assert copies[0] == copies[1]
    assert copies[1] == copies[2]
    assert f.data in copies[-1]

def test_macos_mount():
    h = Volume()
    h.name = 'ElmoTest'
    hf = File()
    hf.data = b'12345' * 10
    for i in reversed(range(100)):
        last = 'testfile-%03d' % i
        h[last] = hf
    ser = h.write(10*1024*1024)

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
    recovered = open('/Volumes/ElmoTest/' + last,'rb').read()
    os.system('umount /Volumes/ElmoTest')
    assert recovered == hf.data

    h2 = Volume()
    h2.read(ser)
    assert h2['testfile-000'].data == hf.data

# def test_extents_overflow():
#     h = Volume()
#     h.read(open('SourceForEmulator.dmg','rb').read())
#     assert h['aa'].data == b'a' * 278528

def test_many_sizes():
    sizes = [800*1024, 1024*1024]
    while sizes[-1] < 4*1024*1024*1024:
        sizes.append(sizes[-1] * 2)

    # okay, we have heaps of sizes
    v = Volume()
    v.name = 'ImportantTestVol'
    for s in sizes:
        ser = v.write(s-512)
        open('/tmp/SMALL-%X.dmg'%s, 'wb').write(ser)
