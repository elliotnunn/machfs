import struct
import copy

def _split_bnode(buf, start):
    """Slice a btree node into records, including the node descriptor"""
    ndFLink, ndBLink, ndType, ndNHeight, ndNRecs = struct.unpack_from('>LLBBH', buf, start)
    offsets = list(reversed(struct.unpack_from('>%dH'%(ndNRecs+1), buf, start+512-2*(ndNRecs+1))))
    starts = offsets[:-1]
    stops = offsets[1:]
    records = [bytes(buf[start+i_start:start+i_stop]) for (i_start, i_stop) in zip(starts, stops)]
    return ndFLink, ndBLink, ndType, ndNHeight, records


def _join_bnode(buf, start, ndFLink, ndBLink, ndType, ndNHeight, records):
    buf[start:start+512] = bytes(512)

    next_left = 14
    next_right = 510

    for r in records:
        if next_left + len(r) > next_right - 2: raise ValueError('cannot fit these records in a B*-tree node')

        buf[start+next_left:start+next_left+len(r)] = r
        struct.pack_into('>H', buf, start+next_right, next_left)

        next_left += len(r)
        next_right -= 2

    struct.pack_into('>H', buf, start+next_right, next_left) # offset of free space

    struct.pack_into('>LLBBH', buf, start, ndFLink, ndBLink, ndType, ndNHeight, len(records))


def _deser_btree(buf, start):
    """Walk an HFS B*-tree, returning an iterator of (key, value) tuples.

    Only leaf nodes are used. Housekeeping data is ignored.
    """

    # Get the header node
    ndFLink, ndBLink, ndType, ndNHeight, (header_rec, unused_rec, map_rec) = _split_bnode(buf, start)

    # Ask about the header record in the header node
    bthDepth, bthRoot, bthNRecs, bthFNode, bthLNode, bthNodeSize, bthKeyLen, bthNNodes, bthFree = \
    struct.unpack_from('>HLLLLHHLL', header_rec)

    this_leaf = bthFNode
    while True:
        ndFLink, ndBLink, ndType, ndNHeight, records = _split_bnode(buf, start+512*this_leaf)

        for rec in records:
            key = rec[1:1+rec[0]]
            val = rec[1+rec[0]:]
            yield key, val

        if this_leaf == bthLNode:
            break
        this_leaf = ndFLink


def _ser_btree(buf, start, stop, btree_dict):
    pass

# the above two functions should make this way easier!

# hell... can I just read the catalog file into a dict, and then
# dump it back when finished? With lazy back-and-forth?


def _from_tuple(val):
    if len(val) == 1:
        return val[0]
    else:
        return val

def _to_tuple(val):
    if isinstance(val, tuple):
        return val
    else:
        return (val,)

def _field(offset, fmt, doc=''):
    fget = lambda self: _from_tuple(struct.unpack_from(fmt, self.buf, offset))
    fset = lambda self, val: struct.pack_into(fmt, self.buf, offset, _to_tuple(val))
    prop = property(fget, fset)
    if doc:
        prop.__doc__ = doc
    return prop

def _mobilefield(offset, fmt, doc=''):
    fget = lambda self: _from_tuple(struct.unpack_from(fmt, self.buf, self.structoffset+offset))
    fset = lambda self, val: struct.pack_into(fmt, self.buf, self.structoffset+offset, _to_tuple(val))
    prop = property(fget, fset)
    if doc:
        prop.__doc__ = doc
    return prop

class HFS:
    bbID = _field(0, '>H', doc='boot blocks signature')
    bbEntry = _field(2, '>L', doc='entry point to boot code')
    bbVersion = _field(6, '>H', doc='boot blocks version number')
    bbPageFlags = _field(8, '>H', doc='used internally')
    bbSysName = _field(10, '16p', doc='System filename')
    bbShellName = _field(26, '16p', doc='Finder filename')
    bbDbg1Name = _field(42, '16p', doc='debugger filename')
    bbDbg2Name = _field(58, '16p', doc='debugger filename')
    bbScreenName = _field(74, '16p', doc='name of startup screen')
    bbHelloName = _field(90, '16p', doc='name of startup program')
    bbScrapName = _field(106, '16p', doc='name of system scrap file')
    bbCntFCBs = _field(122, '>H', doc='number of FCBs to allocate')
    bbCntEvts = _field(124, '>H', doc='number of event queue elements')
    bb128KSHeap = _field(126, '>L', doc='system heap size on 128K Mac')
    bb256KSHeap = _field(130, '>L', doc='used internally')
    bbSysHeapSize = _field(134, '>L', doc='system heap size on all machines')
    bbFiller = _field(138, '>H', doc='reserved')
    bbSysHeapExtra = _field(140, '>L', doc='additional system heap space')
    bbSysHeapFract = _field(144, '>L', doc='fraction of RAM for system heap')

    drSigWord = _field(1024+0, '>H', doc='volume signature')
    drCrDate = _field(1024+2, '>L', doc='date and time of volume creation')
    drLsMod = _field(1024+6, '>L', doc='date and time of last modification')
    drAtrb = _field(1024+10, '>H', doc='volume attributes')
    drNmFls = _field(1024+12, '>H', doc='number of files in root directory')
    drVBMSt = _field(1024+14, '>H', doc='first block of volume bitmap')
    drAllocPtr = _field(1024+16, '>H', doc='start of next allocation search')
    drNmAlBlks = _field(1024+18, '>H', doc='number of allocation blocks in volume')
    drAlBlkSiz = _field(1024+20, '>L', doc='size (in bytes) of allocation blocks')
    drClpSiz = _field(1024+24, '>L', doc='default clump size')
    drAlBlSt = _field(1024+28, '>H', doc='first allocation block in volume')
    drNxtCNID = _field(1024+30, '>L', doc='next unused catalog node ID')
    drFreeBks = _field(1024+34, '>H', doc='number of unused allocation blocks')
    drVN = _field(1024+36, '28p', doc='volume name Pascal string')
    drVolBkUp = _field(1024+64, '>L', doc='date and time of last backup')
    drVSeqNum = _field(1024+68, '>H', doc='volume backup sequence number')
    drWrCnt = _field(1024+70, '>L', doc='volume write count')
    drXTClpSiz = _field(1024+74, '>L', doc='clump size for extents overflow file')
    drCTClpSiz = _field(1024+78, '>L', doc='clump size for catalog file')
    drNmRtDirs = _field(1024+82, '>H', doc='number of directories in root directory')
    drFilCnt = _field(1024+84, '>L', doc='number of files in volume')
    drDirCnt = _field(1024+88, '>L', doc='number of directories in volume')
    drFndrInfo = _field(1024+92, '32s', doc='information used by the Finder')
    drVCSize = _field(1024+124, '>H', doc='size (in blocks) of volume cache')
    drVBMCSize = _field(1024+126, '>H', doc='size (in blocks) of volume bitmap cache')
    drCtlCSize = _field(1024+128, '>H', doc='size (in blocks) of common volume cache')
    drXTFlSize = _field(1024+130, '>L', doc='size of extents overflow file')
    drXTExtRec = _field(1024+134, '>6H', doc='extent record for extents overflow file')
    drCTFlSize = _field(1024+146, '>L', doc='size of catalog file')
    drCTExtRec = _field(1024+150, '>6H', doc='extent record for catalog file')

    ndFLink = _mobilefield(0, '>L', doc='forward link')
    ndBLink = _mobilefield(4, '>L', doc='backward link')
    ndType = _mobilefield(8, '>B', doc='node type')
    ndIndxNode = 0x00; ndHdrNode = 0x01; ndMapNode = 0x02; ndLeafNode = 0xFF
    ndNHeight = _mobilefield(9, '>L', doc='node level')
    ndNRecs = _mobilefield(10, '>H', doc='number of records in node')
    ndResv2 = _mobilefield(12, '>H', doc='reserved')

    bthDepth = _mobilefield(14+0, '>H', doc='current depth of tree')
    bthRoot = _mobilefield(14+2, '>L', doc='number of root node')
    bthNRecs = _mobilefield(14+6, '>L', doc='number of leaf records in tree')
    bthFNode = _mobilefield(14+10, '>L', doc='number of first leaf node')
    bthLNode = _mobilefield(14+14, '>L', doc='number of last leaf node')
    bthNodeSize = _mobilefield(14+18, '>H', doc='size of a node')
    bthKeyLen = _mobilefield(14+20, '>H', doc='maximum length of a key')
    bthNNodes = _mobilefield(14+22, '>L', doc='total number of nodes in tree')
    bthFree = _mobilefield(14+26, '>L', doc='number of free nodes')

    def _dump_attrs(self, prefix=''):
        print('Dumping %s*:' % prefix)
        for key in (k for k in dir(self) if k.startswith(prefix)):
            print('', key, hex(getattr(self, key)))

    def ablk_offset(self, ablkidx):
        """Get byte offset from alloc block (ablk) number"""
        bits_per_pblk = 512 * 8
        ignoreblks = self.drVBMSt + (self.drNmAlBlks + bits_per_pblk - 1) // bits_per_pblk
        return ignoreblks * 512 + ablkidx * self.drAlBlkSiz

    def __init__(self, buf):
        self.structoffset = 0
        self.buf = buf
        self.cache = {}

    def __add__(self, structoffset):
        cp = copy.copy(self)
        cp.structoffset += structoffset
        return cp
    def __sub__(self, negoffset):
        return self.__add__(-negoffset)

    def clrcache(self):
        """Clear the cache because external code has changed the buffer."""
        self.cache.clear()

    def walk_catalog(self):
        catalog_offset = self.ablk_offset(self.drCTExtRec[0])
        bt = _deser_btree(self.buf, catalog_offset)
        for key, val in bt.items():
            print(key, val)



import sys
if sys.argv[1:]:
    infile = sys.argv[1]
else:
    infile = 'SourceForEmulator.dmg'

h = HFS(bytearray(open(infile,'rb').read()))

h.walk_catalog()
















































