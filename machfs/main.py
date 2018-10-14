import struct
from . import btree, bitmanip, directory


def _catalog_rec_sort(b):
    order = [
        0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
        0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f,
        0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17,
        0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f,

        0x20, 0x22, 0x23, 0x28, 0x29, 0x2a, 0x2b, 0x2c,
        0x2f, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36,
        0x37, 0x38, 0x39, 0x3a, 0x3b, 0x3c, 0x3d, 0x3e,
        0x3f, 0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46,

        0x47, 0x48, 0x58, 0x5a, 0x5e, 0x60, 0x67, 0x69,
        0x6b, 0x6d, 0x73, 0x75, 0x77, 0x79, 0x7b, 0x7f,
        0x8d, 0x8f, 0x91, 0x93, 0x96, 0x98, 0x9f, 0xa1,
        0xa3, 0xa5, 0xa8, 0xaa, 0xab, 0xac, 0xad, 0xae,

        0x54, 0x48, 0x58, 0x5a, 0x5e, 0x60, 0x67, 0x69,
        0x6b, 0x6d, 0x73, 0x75, 0x77, 0x79, 0x7b, 0x7f,
        0x8d, 0x8f, 0x91, 0x93, 0x96, 0x98, 0x9f, 0xa1,
        0xa3, 0xa5, 0xa8, 0xaf, 0xb0, 0xb1, 0xb2, 0xb3,

        0x4c, 0x50, 0x5c, 0x62, 0x7d, 0x81, 0x9a, 0x55,
        0x4a, 0x56, 0x4c, 0x4e, 0x50, 0x5c, 0x62, 0x64,
        0x65, 0x66, 0x6f, 0x70, 0x71, 0x72, 0x7d, 0x89,
        0x8a, 0x8b, 0x81, 0x83, 0x9c, 0x9d, 0x9e, 0x9a,

        0xb4, 0xb5, 0xb6, 0xb7, 0xb8, 0xb9, 0xba, 0x95,
        0xbb, 0xbc, 0xbd, 0xbe, 0xbf, 0xc0, 0x52, 0x85,
        0xc1, 0xc2, 0xc3, 0xc4, 0xc5, 0xc6, 0xc7, 0xc8,
        0xc9, 0xca, 0xcb, 0x57, 0x8c, 0xcc, 0x52, 0x85,

        0xcd, 0xce, 0xcf, 0xd0, 0xd1, 0xd2, 0xd3, 0x26,
        0x27, 0xd4, 0x20, 0x4a, 0x4e, 0x83, 0x87, 0x87,
        0xd5, 0xd6, 0x24, 0x25, 0x2d, 0x2e, 0xd7, 0xd8,
        0xa7, 0xd9, 0xda, 0xdb, 0xdc, 0xdd, 0xde, 0xdf,

        0xe0, 0xe1, 0xe2, 0xe3, 0xe4, 0xe5, 0xe6, 0xe7,
        0xe8, 0xe9, 0xea, 0xeb, 0xec, 0xed, 0xee, 0xef,
        0xf0, 0xf1, 0xf2, 0xf3, 0xf4, 0xf5, 0xf6, 0xf7,
        0xf8, 0xf9, 0xfa, 0xfb, 0xfc, 0xfd, 0xfe, 0xff,
    ]

    b = b[0] # we are only sorting keys!

    return b[:4] + bytes(order[ch] for ch in b[5:])


def _suggest_allocblk_size(volsize, minalign):
    min_nonalloc_blks = 6 # just for this estimation
    retval = minalign
    while volsize - min_nonalloc_blks*512 > retval*65536:
        retval += minalign
    return retval


class _TempWrapper:
    """Volume uses this to store metadata while serialising"""
    def __init__(self, of):
        self.of = of


class Folder(directory.AbstractFolder):
    def __init__(self):
        super().__init__()

        self.flags = 0 # help me!
        self.x = 0 # where to put this spatially?
        self.y = 0

        self.crdat = self.mddat = self.bkdat = 0


class File:
    def __init__(self):
        self.type = b'????'
        self.creator = b'????'
        self.flags = 0 # help me!
        self.x = 0 # where to put this spatially?
        self.y = 0

        self.locked = False
        self.crdat = self.mddat = self.bkdat = 0

        self.rsrc = bytearray()
        self.data = bytearray()

    def __str__(self):
        typestr, creatorstr = (x.decode('mac_roman') for x in (self.type, self.creator))
        dstr, rstr = (repr(bytes(x)) if 1 <= len(x) <= 32 else '%db' % len(x) for x in (self.data, self.rsrc))
        return '[%s/%s] data=%s rsrc=%s' % (typestr, creatorstr, dstr, rstr)


class Volume(directory.AbstractFolder):
    def __init__(self):
        super().__init__()

        self.bootblocks = bytes(1024)       # optional; for booting HFS volumes
        self.crdate = 0                     # date and time of volume creation
        self.lsmod = 0                      # date and time of last modification
        self.name = 'Untitled'

    def read(self, from_volume):
        self.bootblocks = from_volume[:1024]

        drSigWord, drCrDate, drLsMod, drAtrb, drNmFls, \
        drVBMSt, drAllocPtr, drNmAlBlks, drAlBlkSiz, drClpSiz, drAlBlSt, \
        drNxtCNID, drFreeBks, drVN, drVolBkUp, drVSeqNum, \
        drWrCnt, drXTClpSiz, drCTClpSiz, drNmRtDirs, drFilCnt, drDirCnt, \
        drFndrInfo, drVCSize, drVBMCSize, drCtlCSize, \
        drXTFlSize, drXTExtRec, \
        drCTFlSize, drCTExtRec, \
        = struct.unpack_from('>2sLLHHHHHLLHLH28pLHLLLHLL32sHHHL12sL12s', from_volume, 1024)

        self.crdate = drCrDate
        self.lsmod = drLsMod
        self.name = drVN.decode('mac_roman')

        block2offset = lambda block: 512*drAlBlSt + drAlBlkSiz*block
        extent2bytes = lambda firstblk, blkcnt: from_volume[block2offset(firstblk):block2offset(firstblk+blkcnt)]
        extrec2bytes = lambda extrec: b''.join(extent2bytes(a, b) for (a, b) in btree.unpack_extent_record(extrec))

        extoflow = {}
        for rec in btree.dump_btree(extrec2bytes(drXTExtRec)):
            if rec[0] != 7: continue
            xkrFkType, xkrFNum, xkrFABN, extrec = struct.unpack_from('>xBLH12s', rec)
            if xkrFkType == 0xFF:
                fork = 'rsrc'
            elif xkrFkType == 0:
                fork = 'data'
            extoflow[xkrFNum, fork, xkrFABN] = extrec

        cnids = {}
        childlist = [] # list of (parent_cnid, child_name, child_object) tuples

        prev_key = None
        for rec in btree.dump_btree(extrec2bytes(drCTExtRec)):
            # create a directory tree from the catalog file
            rec_len = rec[0]
            if rec_len == 0: continue

            key = rec[2:1+rec_len]
            val = rec[bitmanip.pad_up(1+rec_len, 2):]

            # if prev_key: # Uncomment this to test the sort order with 20% performance cost!
            #     if _catalog_rec_sort((prev_key,)) >= _catalog_rec_sort((key,)):
            #         raise ValueError('Sort error: %r, %r' % (prev_key, key))
            # prev_key = key

            ckrParID, namelen = struct.unpack_from('>LB', key)
            ckrCName = key[5:5+namelen]

            datatype = (None, 'dir', 'file', 'dthread', 'fthread')[val[0]]
            datarec = val[2:]

            # print(datatype + '\t' + repr(key))
            # print('\t', datarec)
            # print()

            if datatype == 'dir':
                dirFlags, dirVal, dirDirID, dirCrDat, dirMdDat, dirBkDat, dirUsrInfo, dirFndrInfo \
                = struct.unpack_from('>HHLLLL16s16s', datarec)

                f = Folder()
                cnids[dirDirID] = f
                childlist.append((ckrParID, ckrCName, f))

                f.crdat, f.mddat, f.bkdat = dirCrDat, dirMdDat, dirBkDat

            elif datatype == 'file':
                filFlags, filTyp, filUsrWds, filFlNum, \
                filStBlk, filLgLen, filPyLen, \
                filRStBlk, filRLgLen, filRPyLen, \
                filCrDat, filMdDat, filBkDat, \
                filFndrInfo, filClpSize, \
                filExtRec, filRExtRec, \
                = struct.unpack_from('>BB16sLHLLHLLLLL16sH12s12sxxxx', datarec)

                f = File()
                cnids[filFlNum] = f
                childlist.append((ckrParID, ckrCName, f))

                f.crdat, f.mddat, f.bkdat = filCrDat, filMdDat, filBkDat
                f.type, f.creator, f.flags, f.x, f.y = struct.unpack_from('>4s4sHHH', filUsrWds)

                for fork, length, extrec in [('data', filLgLen, filExtRec), ('rsrc', filRLgLen, filRExtRec)]:
                    accum = bytearray(extrec2bytes(extrec))
                    while len(accum) < length:
                        next_blk = len(accum) // drAlBlkSiz
                        next_extrec = extoflow[filFlNum, fork, next_blk]
                        accum.extend(extrec2bytes(next_extrec))
                    del accum[length:] # logical length can be less than a number of blocks

                    setattr(f, fork, accum)

            # elif datatype == 3:
            #     print('dir thread:', rec)
            # elif datatype == 4:
            #     print('fil thread:', rec)

        for parent_cnid, child_name, child_obj in childlist:
            if parent_cnid != 1:
                parent_obj = cnids[parent_cnid]
                parent_obj[child_name] = child_obj

        self.update(cnids[2])

    def write(self, size=800*1024, align=512):
        if align < 512 or align % 512:
            raise ValueError('align must be multiple of 512')

        if size < 400 * 1024 or size % 512:
            raise ValueError('size must be a multiple of 512b and >= 800K')

        # overall layout:
        #   1. two boot blocks (offset=0)
        #   2. one volume control block (offset=2)
        #   3. some bitmap blocks (offset=3)
        #   4. many allocation blocks
        #   5. duplicate VCB (offset=-2)
        #   6. unused block (offset=-1)

        # so we will our best guess at these variables as we go:
        # drNmAlBlks, drAlBlkSiz, drAlBlSt

        # the smallest possible alloc block size
        drAlBlkSiz = _suggest_allocblk_size(size, align)

        # how many blocks will we use for the bitmap?
        # (cheat by adding blocks to align the alloc area)
        bitmap_blk_cnt = 0
        while (size - (5+bitmap_blk_cnt)*512) // drAlBlkSiz > bitmap_blk_cnt*512*8:
            bitmap_blk_cnt += 1
        while (3+bitmap_blk_cnt)*512 % align:
            bitmap_blk_cnt += 1

        # decide how many alloc blocks there will be
        drNmAlBlks = (size - (5+bitmap_blk_cnt)*512) // drAlBlkSiz
        blkaccum = []

        # <<< put the empty extents overflow file in here >>>
        extoflowfile = btree.make_btree([], bthKeyLen=7, blksize=drAlBlkSiz)
        # also need to do some cleverness to ensure that this gets picked up...
        drXTFlSize = len(extoflowfile)
        drXTExtRec_Start = len(blkaccum)
        blkaccum.extend(bitmanip.chunkify(extoflowfile, drAlBlkSiz))
        drXTExtRec_Cnt = len(blkaccum) - drXTExtRec_Start

        # write all the files in the volume
        topwrap = _TempWrapper(self)
        topwrap.path = (self.name,)
        topwrap.cnid = 2

        godwrap = _TempWrapper(None)
        godwrap.cnid = 1

        path2wrap = {(): godwrap, (self.name,): topwrap}
        drNxtCNID = 16
        for path, obj in self.iter_paths():
            path = (self.name,) + path
            wrap = _TempWrapper(obj)
            path2wrap[path] = wrap
            wrap.path = path
            wrap.cnid = drNxtCNID; drNxtCNID += 1

            if isinstance(obj, File):
                wrap.dfrk = wrap.rfrk = (0, 0)
                if obj.data:
                    pre = len(blkaccum)
                    blkaccum.extend(bitmanip.chunkify(obj.data, drAlBlkSiz))
                    wrap.dfrk = (pre, len(blkaccum)-pre)
                if obj.rsrc:
                    pre = len(blkaccum)
                    blkaccum.extend(bitmanip.chunkify(obj.rsrc, drAlBlkSiz))
                    wrap.rfrk = (pre, len(blkaccum)-pre)

        catalog = [] # (key, value) tuples

        drFilCnt = 0
        drDirCnt = -1 # to exclude the root directory

        for path, wrap in path2wrap.items():
            if wrap.cnid == 1: continue

            obj = wrap.of
            pstrname = bitmanip.pstring(path[-1])

            mainrec_key = struct.pack('>L', path2wrap[path[:-1]].cnid) + pstrname

            if isinstance(wrap.of, File):
                drFilCnt += 1

                cdrType = 2
                filFlags = 1 << 1 # file thread record exists, but is not locked, nor "file record is used"
                filTyp = 0
                filUsrWds = struct.pack('>4s4sHHHxxxxxx', obj.type, obj.creator, obj.flags, obj.x, obj.y)
                filFlNum = wrap.cnid
                filStBlk, filLgLen, filPyLen = wrap.dfrk[0], len(obj.data), bitmanip.pad_up(len(obj.data), drAlBlkSiz)
                filRStBlk, filRLgLen, filRPyLen = wrap.rfrk[0], len(obj.rsrc), bitmanip.pad_up(len(obj.rsrc), drAlBlkSiz)
                filCrDat, filMdDat, filBkDat = obj.crdat, obj.mddat, obj.bkdat
                filFndrInfo = bytes(16) # todo must fix
                filClpSize = 0 # todo must fix
                filExtRec = struct.pack('>HHHHHH', *wrap.dfrk, 0, 0, 0, 0)
                filRExtRec = struct.pack('>HHHHHH', *wrap.rfrk, 0, 0, 0, 0)

                mainrec_val = struct.pack('>BxBB16sLHLLHLLLLL16sH12s12sxxxx',
                    cdrType, \
                    filFlags, filTyp, filUsrWds, filFlNum, \
                    filStBlk, filLgLen, filPyLen, \
                    filRStBlk, filRLgLen, filRPyLen, \
                    filCrDat, filMdDat, filBkDat, \
                    filFndrInfo, filClpSize, \
                    filExtRec, filRExtRec, \
                )

            else: # assume directory
                drDirCnt += 1

                cdrType = 1
                dirFlags = 0 # must fix
                dirVal = len(wrap.of)
                dirDirID = wrap.cnid
                dirCrDat, dirMdDat, dirBkDat = (0,0,0) if obj is self else (obj.crdat, obj.mddat, obj.bkdat)
                dirUsrInfo = bytes(16)
                dirFndrInfo = bytes(16)
                mainrec_val = struct.pack('>BxHHLLLL16s16sxxxxxxxxxxxxxxxx',
                    cdrType, dirFlags, dirVal, dirDirID,
                    dirCrDat, dirMdDat, dirBkDat,
                    dirUsrInfo, dirFndrInfo,
                )

            catalog.append((mainrec_key, mainrec_val))

            thdrec_key = struct.pack('>Lx', wrap.cnid)
            thdrec_val_type = 4 if isinstance(wrap.of, File) else 3
            thdrec_val = struct.pack('>BxxxxxxxxxL', thdrec_val_type, path2wrap[path[:-1]].cnid) + pstrname

            catalog.append((thdrec_key, thdrec_val))


        # now it is time to sort these records! fuck that shit...
        catalog.sort(key=_catalog_rec_sort)
        catalogfile = btree.make_btree(catalog, bthKeyLen=37, blksize=drAlBlkSiz)
        # also need to do some cleverness to ensure that this gets picked up...
        drCTFlSize = len(catalogfile)
        drCTExtRec_Start = len(blkaccum)
        blkaccum.extend(bitmanip.chunkify(catalogfile, drAlBlkSiz))
        drCTExtRec_Cnt = len(blkaccum) - drCTExtRec_Start

        if len(blkaccum) > drNmAlBlks:
            raise ValueError('Does not fit!')

        # Create the bitmap of free volume allocation blocks
        bitmap = bitmanip.bits(bitmap_blk_cnt * 512 * 8, len(blkaccum))

        # Create the Volume Information Block
        drSigWord = b'BD'
        drNmFls = sum(isinstance(x, File) for x in self.values())
        drNmRtDirs = sum(not isinstance(x, File) for x in self.values())
        drVBMSt = 3 # first block of volume bitmap
        drAllocPtr = 0
        drClpSiz = drXTClpSiz = drCTClpSiz = drAlBlkSiz
        drAlBlSt = 3 + bitmap_blk_cnt
        drFreeBks = drNmAlBlks - len(blkaccum)
        drWrCnt = 0 # ????volume write count
        drVCSize = drVBMCSize = drCtlCSize = 0
        drAtrb = 1<<8                  # volume attributes (hwlock, swlock, CLEANUNMOUNT, badblocks)
        drVN = self.name.encode('mac_roman')
        drVolBkUp = 0                  # date and time of last backup
        drVSeqNum = 0                  # volume backup sequence number
        drFndrInfo = bytes(32)         # information used by the Finder
        drCrDate = self.crdate
        drLsMod = self.lsmod

        if not (1 <= len(drVN) <= 27):
            raise ValueError('Volume name range 1-27 chars')

        vib = struct.pack('>2sLLHHHHHLLHLH28pLHLLLHLL32sHHHLHHxxxxxxxxLHHxxxxxxxx',
            drSigWord, drCrDate, drLsMod, drAtrb, drNmFls,
            drVBMSt, drAllocPtr, drNmAlBlks, drAlBlkSiz, drClpSiz, drAlBlSt,
            drNxtCNID, drFreeBks, drVN, drVolBkUp, drVSeqNum,
            drWrCnt, drXTClpSiz, drCTClpSiz, drNmRtDirs, drFilCnt, drDirCnt,
            drFndrInfo, drVCSize, drVBMCSize, drCtlCSize,
            drXTFlSize, drXTExtRec_Start, drXTExtRec_Cnt,
            drCTFlSize, drCTExtRec_Start, drCTExtRec_Cnt,
        )
        vib += bytes(512-len(vib))

        assert all(len(x) == drAlBlkSiz for x in blkaccum)
        finalchunks = [self.bootblocks, vib, bitmap, *blkaccum]
        finalchunks.append(bytes(size - sum(len(x) for x in finalchunks) - 2*512))
        finalchunks.append(vib)
        finalchunks.append(bytes(512))
        return b''.join(finalchunks)
