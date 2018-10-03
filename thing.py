import struct
import collections


def _pad_up(size, factor):
    x = size + factor - 1
    return x - (x % factor)

def _split_bnode(buf, start):
    """Slice a btree node into records, including the node descriptor"""
    ndFLink, ndBLink, ndType, ndNHeight, ndNRecs = struct.unpack_from('>LLBBH', buf, start)
    offsets = list(reversed(struct.unpack_from('>%dH'%(ndNRecs+1), buf, start+512-2*(ndNRecs+1))))
    starts = offsets[:-1]
    stops = offsets[1:]
    records = [bytes(buf[start+i_start:start+i_stop]) for (i_start, i_stop) in zip(starts, stops)]
    return ndFLink, ndBLink, ndType, ndNHeight, records

def _dump_btree_recs(buf, start):
    """Walk an HFS B*-tree, returning an iterator of (key, value) tuples."""

    # Get the header node
    ndFLink, ndBLink, ndType, ndNHeight, (header_rec, unused_rec, map_rec) = _split_bnode(buf, start)

    # Ask about the header record in the header node
    bthDepth, bthRoot, bthNRecs, bthFNode, bthLNode, bthNodeSize, bthKeyLen, bthNNodes, bthFree = \
    struct.unpack_from('>HLLLLHHLL', header_rec)
    # print('btree', bthDepth, bthRoot, bthNRecs, bthFNode, bthLNode, bthNodeSize, bthKeyLen, bthNNodes, bthFree)

    # And iterate through the linked list of leaf nodes
    this_leaf = bthFNode
    while True:
        ndFLink, ndBLink, ndType, ndNHeight, records = _split_bnode(buf, start+512*this_leaf)

        yield from records

        if this_leaf == bthLNode:
            break
        this_leaf = ndFLink

def _pack_leaf_record(key, value): # works correctly
    b = bytes([len(key)+1, 0, *key])
    if len(b) & 1: b += bytes(1)
    b += value
    return b

def _pack_index_record(key, pointer):
    key += bytes(0x24 - len(key))
    value = struct.pack('>L', pointer)
    return _pack_leaf_record(key, value)

def _will_fit_in_leaf_node(keyvals):
    return len(keyvals) <= 2 # really must fix this!

def _will_fit_in_index_node(keyvals):
    return len(keyvals) <= 8

def _bits(ntotal, nset):
    nset = max(nset, 0)
    nset = min(nset, ntotal)
    a = b'\xFF' * (nset // 8)
    c = b'\x00' * ((ntotal-nset) // 8)
    if (len(a) + len(c)) * 8 < ntotal:
        b = [b'\x00', b'\x80', b'\xC0', b'\xE0', b'\xF0', b'\xF8', b'\xFC', b'\xFE', b'\xFF'][nset % 8]
        return b''.join([a,b,c])
    else:
        return b''.join([a,c])

class _Node:
    def __bytes__(self):
        buf = bytearray(512)

        next_left = 14
        next_right = 510

        for r in self.records:
            if next_left + len(r) > next_right - 2:
                raise ValueError('cannot fit these records in a B*-tree node')

            buf[next_left:next_left+len(r)] = r
            struct.pack_into('>H', buf, next_right, next_left)

            next_left += len(r)
            next_right -= 2

        struct.pack_into('>H', buf, next_right, next_left) # offset of free space

        struct.pack_into('>LLBBH', buf, 0,
            self.ndFLink, self.ndBLink, self.ndType, self.ndNHeight, len(self.records))

        return bytes(buf)

def _mkbtree(records):
    biglist = [[[]]] # [level][node][record]
    bthNRecs = 0

    for keyval in records:
        bthNRecs += 1
        curnode = biglist[-1][-1]
        curnode.append(keyval)
        if not _will_fit_in_leaf_node(curnode):
            del curnode[-1]
            curnode = [keyval]
            biglist[-1].append(curnode)

    while len(biglist[-1]) > 1:
        biglist.append([[]])

        for prevnode in biglist[-2]:
            keyval = prevnode[0]
            curnode = biglist[-1][-1]
            curnode.append(keyval)
            if not _will_fit_in_index_node(curnode):
                del curnode[-1]
                curnode = [keyval]
                biglist[-1].append(curnode)

    biglist.reverse() # index nodes then leaf nodes

    # cool, now biglist is of course brilliant
    for i, level in enumerate(biglist, 1):
        print('LEVEL', i)
        for node in level:
            print('(%d)' % len(node), *(rec[0] for rec in node))
        print()

    # Make space for a header node at element 0
    hnode = _Node()
    nodelist = [hnode]
    hnode.ndNHeight = 0
    hnode.records = [bytes(106), bytes(128), bytes(256)]
    hnode.ndType = 1

    spiderdict = {} # maps (level, key) to index

    for i, level in enumerate(biglist, 1):
        for node in level:
            if len(node) == 0: continue
            firstkey, firstval = node[0]
            spiderdict[i, firstkey] = len(nodelist)

            newnode = _Node()
            nodelist.append(newnode)
            newnode.records = node
            newnode.ndNHeight = i

            if level is biglist[-1]:
                newnode.ndType = 0xFF # leaf node
            else:
                newnode.ndType = 0 # index node

    # for n in nodelist:
    #     print(n.ndNHeight, n.records)
    #     print()

    # print(spiderdict)

    # pack the records in the index and leaf nodes
    for node in nodelist:
        if node.ndType == 0xFF: # leaf node
            node.records = [_pack_leaf_record(k, v) for (k, v) in node.records]
        elif node.ndType == 0: # index node
            node.records = [_pack_index_record(k, spiderdict[node.ndNHeight+1, k]) for (k, v) in node.records]

    # make the map nodes so that the bitmap covers what we use
    # (this does not yet populate the bitmap)
    bits_covered = 2048
    mapnodes = []
    while bits_covered < len(nodelist):
        print('making map node!')
        bits_covered += 3952 # bits in a max-sized record
        mapnode = _Node()
        nodelist.append(mapnode)
        mapnodes.append(mapnode)
        mapnode.ndType = 2
        ndNHeight = 1 # fix, not sure about this
        mapnode.records = [] # fix this

    # now we run back and forth to join up nodes of similar type
    most_recent = {}
    for i, node in enumerate(nodelist):
        node.ndBLink = most_recent.get(node.ndType, 0)
        most_recent[node.ndType] = i
    bthLNode = most_recent.get(0xFF, 0)
    most_recent = {}
    for i, node in reversed(list(enumerate(nodelist))):
        node.ndFLink = most_recent.get(node.ndType, 0)
        most_recent[node.ndType] = i
    bthFNode = most_recent.get(0xFF, 0)

    # for n in nodelist:
    #     print(n.__dict__)

    bthFree = len(nodelist) // 4 # maybe limber this up in the future

    # populate the bitmap (1 = used)
    hnode.records[2] = _bits(2048, len(nodelist))
    for i, mnode in mapnodes:
        nset = len(nodelist) - 2048 - i*3952
        mnode.records = [_bits(3952, nset)]

    # populate the header node:
    bthDepth = len(biglist)
    bthRoot = 1 # root node is first-but-one
    # bthNRecs set above
    # bthFNode/bthLNode also set above
    bthNodeSize = 512
    bthKeyLen = 37
    bthNNodes = len(nodelist) + bthFree # how do we calculate this?
    # bthFree set above
    hnode.records[0] = struct.pack('>HLLLLHHLL76x',
        bthDepth, bthRoot, bthNRecs, bthFNode, bthLNode,
        bthNodeSize, bthKeyLen, bthNNodes, bthFree)

    # last little hack: append free nodes to nodelist
    nodelist.append(512 * bthFree) # these will become zeroes
    return b''.join(bytes(node) for node in nodelist)

def _catrec_sorter(b):
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
        return 'File %r/%r data=%db rsrc=%db' % (self.type, self.creator, len(self.data), len(self.rsrc))


class _AbstractFolder(dict):
    def paths(self):
        for name, child in self.items():
            yield ((name,), child)
            try:
                childs_children = child.paths()
            except AttributeError:
                pass
            else:
                for each_path, each_child in childs_children:
                    yield (name,) + each_path, each_child

    def __str__(self):
        return 'Folder valence=%d' % len(self)


class Folder(_AbstractFolder):
    def __init__(self):
        super().__init__()

        self.flags = 0 # help me!
        self.x = 0 # where to put this spatially?
        self.y = 0

        self.crdat = self.mddat = self.bkdat = 0


def _chunkify(b, blksize):
    for i in range(0, len(b), blksize):
        ab = b[i:i+blksize]
        if len(ab) < blksize: ab += bytes(blksize-len(ab))
        yield ab


class _TempWrapper:
    def __init__(self, of):
        self.of = of


class Volume(_AbstractFolder):
    def __init__(self):
        super().__init__()

        self.bootblocks = bytes(1024)       # optional; for booting HFS volumes
        self.drCrDate = 0                   # date and time of volume creation
        self.drLsMod = 0                    # date and time of last modification
        self.drAtrb = 0                     # volume attributes (hwlock, swlock, cleanunmount, badblocks)
        self.drVN = b'Untitled'             # volume name Pascal string
        self.drVolBkUp = 0                  # date and time of last backup
        self.drVSeqNum = 0                  # volume backup sequence number
        self.drFndrInfo = bytes(32)         # information used by the Finder

    def read(self, from_volume):
        self._dirtree = {}
        self.bootblocks = from_volume[:1024]

        drSigWord, self.drCrDate, self.drLsMod, self.drAtrb, drNmFls, \
        drVBMSt, drAllocPtr, drNmAlBlks, drAlBlkSiz, drClpSiz, drAlBlSt, \
        drNxtCNID, drFreeBks, self.drVN, self.drVolBkUp, self.drVSeqNum, \
        drWrCnt, drXTClpSiz, drCTClpSiz, drNmRtDirs, drFilCnt, drDirCnt, \
        self.drFndrInfo, drVCSize, drVBMCSize, drCtlCSize, \
        drXTFlSize, drXTExtRec_Start, drXTExtRec_Cnt, _, _, _, _, \
        drCTFlSize, drCTExtRec_Start, drCTExtRec_Cnt, _, _, _, _, \
        = struct.unpack_from('>2sLLHHHHHLLHLH28pLHLLLHLL32sHHHL6HL6H', from_volume, 1024)

        extoflow = {}

        for rec in _dump_btree_recs(from_volume, 512*drAlBlSt + drAlBlkSiz*drXTExtRec_Start):
            if rec[0] != 7: continue
            # print(key, val)
            pass

        cnids = {}
        childrenof = collections.defaultdict(dict)

        for rec in _dump_btree_recs(from_volume, 512*drAlBlSt + drAlBlkSiz*drCTExtRec_Start):
            # create a directory tree from the catalog file
            rec_len = rec[0]
            if rec_len == 0: continue

            key = rec[2:1+rec_len]
            val = rec[_pad_up(1+rec_len, 2):]

            ckrParID, namelen = struct.unpack_from('>LB', key)
            ckrCName = key[6:6+namelen]

            datatype = (None, 'dir', 'file', 'dthread', 'fthread')[val[0]]
            datarec = val[2:]

            print(datatype)
            print('\t', key)
            print('\t', datarec)

            if datatype == 'dir':
                dirFlags, dirVal, dirDirID, dirCrDat, dirMdDat, dirBkDat, dirUsrInfo, dirFndrInfo \
                = struct.unpack_from('>HHLLLL16s16s', datarec)

                f = Folder()
                cnids[dirDirID] = f
                childrenof[ckrParID][ckrCName] = f

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
                childrenof[ckrParID][ckrCName] = f

                f.crdat, f.mddat, f.bkdat = filCrDat, filMdDat, filBkDat
                f.type, f.creator, f.flags, f.x, f.y = struct.unpack_from('>4s4sHHH', filUsrWds)

                for fork, length, extrec in [('data', filLgLen, filExtRec), ('rsrc', filRLgLen, filRExtRec)]:
                    accum = bytearray()
                    extrec = list(struct.unpack('>HHHHHH', extrec))
                    extrec = list(zip(extrec[::2], extrec[1::2]))
                    for extstart, extlength in extrec:
                        if extlength == 0: continue
                        astart = 512*drAlBlSt + drAlBlkSiz*extstart
                        astop = astart + drAlBlkSiz*extlength
                        accum.extend(from_volume[astart:astop])
                    del accum[length:] # logical length can be less than a number of blocks
                    if len(accum) != length:
                        raise ValueError('need to consult extents overflow file')

                    setattr(f, fork, accum)

            # elif datatype == 3:
            #     print('dir thread:', rec)
            # elif datatype == 4:
            #     print('fil thread:', rec)

        for parent, children in childrenof.items():
            if parent != 1: # not the mythical parent of root!
                cnids[parent].update(children)

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
        extoflowfile = _mkbtree([])
        # also need to do some cleverness to ensure that this gets picked up...
        drXTFlSize = len(extoflowfile)
        drXTExtRec_Start = len(blkaccum)
        blkaccum.extend(_chunkify(extoflowfile, drAlBlkSiz))
        drXTExtRec_Cnt = len(blkaccum) - drXTExtRec_Start

        # write all the files in the volume
        topwrap = _TempWrapper(self)
        topwrap.path = (self.drVN,)
        topwrap.cnid = 2

        godwrap = _TempWrapper(None)
        godwrap.cnid = 1

        path2wrap = {(): godwrap, (self.drVN,): topwrap}
        drNxtCNID = 16
        for path, obj in self.paths():
            path = (self.drVN,) + path
            wrap = _TempWrapper(obj)
            path2wrap[path] = wrap
            wrap.path = path
            wrap.cnid = drNxtCNID; drNxtCNID += 1

            if isinstance(obj, File):
                wrap.dfrk = wrap.rfrk = (0, 0)
                if obj.data:
                    pre = len(blkaccum)
                    blkaccum.extend(_chunkify(obj.data, drAlBlkSiz))
                    wrap.dfrk = (pre, len(blkaccum)-pre)
                if obj.rsrc:
                    pre = len(blkaccum)
                    blkaccum.extend(_chunkify(obj.rsrc, drAlBlkSiz))
                    wrap.rfrk = (pre, len(blkaccum)-pre)

        catalog = [] # (key, value) tuples

        drFilCnt = drDirCnt = 0

        for path, wrap in path2wrap.items():
            if wrap.cnid == 1: continue

            obj = wrap.of

            mainrec_key = struct.pack('>LB', path2wrap[path[:-1]].cnid, len(path[-1])) + path[-1]

            if isinstance(wrap.of, File):
                drFilCnt += 1

                cdrType = 2
                filFlags = 0 # todo must fix
                filTyp = 0
                filUsrWds = struct.pack('>4s4sHHHxxxxxx', obj.type, obj.creator, obj.flags, obj.x, obj.y)
                filFlNum = wrap.cnid
                filStBlk, filLgLen, filPyLen = 0, len(obj.data), _pad_up(len(obj.data), drAlBlkSiz) # todo must fix
                filRStBlk, filRLgLen, filRPyLen = 0, len(obj.rsrc), _pad_up(len(obj.rsrc), drAlBlkSiz) # todo must fix
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
                mainrec_val = struct.pack('>BxHHLLLL16s16sxxxxxxxx',
                    cdrType, dirFlags, dirVal, dirDirID,
                    dirCrDat, dirMdDat, dirBkDat,
                    dirUsrInfo, dirFndrInfo,
                )

            catalog.append((mainrec_key, mainrec_val))

            thdrec_key = struct.pack('>Lx', wrap.cnid)
            thdrec_val_type = 4 if isinstance(wrap.of, File) else 3
            thdrec_val = struct.pack('>BxxxxxxxxxLB', thdrec_val_type, path2wrap[path[:-1]].cnid, len(path[-1])) + path[-1]

            catalog.append((thdrec_key, thdrec_val))

        catalog.sort(key=_catrec_sorter)

        # now it is time to sort these records! fuck that shit...
        # catalog.sort...
        catalogfile = _mkbtree(catalog)
        # also need to do some cleverness to ensure that this gets picked up...
        drCTFlSize = len(catalogfile)
        drCTExtRec_Start = len(blkaccum)
        blkaccum.extend(_chunkify(catalogfile, drAlBlkSiz))
        drCTExtRec_Cnt = len(blkaccum) - drCTExtRec_Start

        if len(blkaccum) > drNmAlBlks:
            raise ValueError('Does not fit!')

        # Create the bitmap of free volume allocation blocks
        bitmap = _bits(bitmap_blk_cnt * 512 * 8, len(blkaccum))

        # Create the Volume Information Block
        drSigWord = b'BD'
        drNmFls = sum(isinstance(x, File) for x in self.values())
        drNmRtDirs = sum(not isinstance(x, File) for x in self.values())
        drVBMSt = 3 # first block of volume bitmap
        drAllocPtr = len(blkaccum)
        drClpSiz = drXTClpSiz = drCTClpSiz = drAlBlkSiz
        drAlBlSt = 3 + bitmap_blk_cnt
        drFreeBks = drNmAlBlks - len(blkaccum)
        drWrCnt = 0 # ????volume write count
        drVCSize = drVBMCSize = drCtlCSize = 99

        vib = struct.pack('>2sLLHHHHHLLHLH28pLHLLLHLL32sHHHLHHxxxxxxxxLHHxxxxxxxx',
            drSigWord, self.drCrDate, self.drLsMod, self.drAtrb, drNmFls,
            drVBMSt, drAllocPtr, drNmAlBlks, drAlBlkSiz, drClpSiz, drAlBlSt,
            drNxtCNID, drFreeBks, self.drVN, self.drVolBkUp, self.drVSeqNum,
            drWrCnt, drXTClpSiz, drCTClpSiz, drNmRtDirs, drFilCnt, drDirCnt,
            self.drFndrInfo, drVCSize, drVBMCSize, drCtlCSize,
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


import sys
if sys.argv[1:]:
    infile = sys.argv[1]
else:
    infile = 'SourceForEmulator.dmg'
import pprint


print(_mkbtree([]))

# h = Volume()
# h.read(open(infile,'rb').read())


# open('/tmp/aj', 'wb').write(h[b'Extensions'][b'AppleJack 2.1'].rsrc)
# pprint.pprint(h)
# for path, obj in h.paths():
#     print(path, obj)


h = Volume()
f = File()
h[b'file'] = f
wr = h.write(800*1024)
open(infile,'wb').write(wr)

h2 = Volume()
h2.read(wr)















































