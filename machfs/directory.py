import collections
import os
from os import path
from macresources import make_rez_code, parse_rez_code, make_file, parse_file


class AbstractFolder(collections.MutableMapping):
    def __init__(self, from_dict=()):
        self._prefdict = {} # lowercase to preferred
        self._maindict = {} # lowercase to contents
        self.update(from_dict)

    def __setitem__(self, key, value):
        try:
            key = key.decode('mac_roman')
        except AttributeError:
            pass

        key.encode('mac_roman')

        lower = key.lower()
        self._prefdict[lower] = key
        self._maindict[lower] = value

    def __getitem__(self, key):
        try:
            key = key.decode('mac_roman')
        except AttributeError:
            pass

        lower = key.lower()
        return self._maindict[lower]

    def __delitem__(self, key):
        try:
            key = key.decode('mac_roman')
        except AttributeError:
            pass

        lower = key.lower()
        del self._maindict[lower]
        del self._prefdict[lower]

    def __iter__(self):
        return iter(self._prefdict.values())

    def __len__(self):
        return len(self._maindict)

    def __repr__(self):
        the_dict = {self._prefdict[k]: v for (k, v) in self._maindict.items()}
        return repr(the_dict)

    def __str__(self):
        lines = []
        for k, v in self.items():
            v = str(v)
            if '\n' in v:
                lines.append(k + ':')
                for l in v.split('\n'):
                    lines.append('  ' + l)
            else:
                lines.append(k + ': ' + v)
        return '\n'.join(lines)

    def iter_paths(self):
        for name, child in self.items():
            yield ((name,), child)
            try:
                childs_children = child.iter_paths()
            except AttributeError:
                pass
            else:
                for each_path, each_child in childs_children:
                    yield (name,) + each_path, each_child

    def read_folder(self, folder_path, date=0, mpw_dates=False):
        def includefilter(n):
            if n.startswith('.'): return False
            if n.endswith('.rdump'): return True
            if n.endswith('.idump'): return True
            return True

        def swapsep(n):
            return n.replace(':', path.sep)

        def mkbasename(n):
            base, ext = path.splitext(n)
            if ext in ('.rdump', '.idump'):
                return base
            else:
                return n

        self.crdate = self.mddate = self.bkdate = date

        tmptree = {folder_path: self}

        for dirpath, dirnames, filenames in os.walk(folder_path):
            dirnames[:] = [swapsep(x) for x in dirnames if includefilter(x)]
            filenames[:] = [swapsep(x) for x in filenames if includefilter(x)]

            for dn in dirnames:
                newdir = Folder()
                newdir.crdate = newdir.mddate = newdir.bkdate = date
                tmptree[dirpath][dn] = newdir
                tmptree[path.join(dirpath, dn)] = newdir

            for fn in filenames:
                basename = mkbasename(fn)
                fullbase = path.join(dirpath, basename)
                fullpath = path.join(dirpath, fn)

                try:
                    thefile = tmptree[fullbase]
                except KeyError:
                    thefile = File()
                    thefile.real_t = 0 # for the MPW hack
                    thefile.crdate = thefile.mddate = thefile.bkdate = date
                    thefile.contributors = []
                    tmptree[fullbase] = thefile

                if fn.endswith('.idump'):
                    with open(fullpath, 'rb') as f:
                        thefile.type = f.read(4)
                        thefile.creator = f.read(4)
                elif fn.endswith('rdump'):
                    rez = open(fullpath, 'rb').read()
                    resources = parse_rez_code(rez)
                    resfork = make_file(resources, align=4)
                    thefile.rsrc = resfork
                else:
                    thefile.data = open(fullpath, 'rb').read()

                thefile.contributors.append(fullpath)
                if mpw_dates:
                    thefile.real_t = max(thefile.real_t, path.getmtime(fullpath))

                tmptree[dirpath][basename] = thefile

        for pathtpl, obj in self.iter_paths():
            try:
                if obj.type == b'TEXT':
                    obj.data = obj.data.decode('utf8').replace('\r\n', '\r').replace('\n', '\r').encode('mac_roman')
            except AttributeError:
                pass

        if mpw_dates:
            all_real_times = set()
            for pathtpl, obj in self.iter_paths():
                try:
                    all_real_times.add(obj.real_t)
                except AttributeError:
                    pass
            ts2idx = {ts: idx for (idx, ts) in enumerate(sorted(set(all_real_times)))}

            for pathtpl, obj in self.iter_paths():
                try:
                    real_t = obj.real_t
                except AttributeError:
                    pass
                else:
                    fake_t = obj.crdate + 60 * ts2idx[real_t]
                    obj.crdate = obj.mddate = obj.bkdate = fake_t

    def write_folder(self, folder_path):
        def any_exists(at_path):
            if path.exists(at_path): return True
            if path.exists(at_path + '.rdump'): return True
            if path.exists(at_path + '.idump'): return True
            return False

        written = []
        for p, obj in self.iter_paths():
            nativepath = path.join(folder_path, *(comp.replace(path.sep, ':') for comp in p))

            if isinstance(obj, Folder):
                os.makedirs(nativepath, exist_ok=True)

            elif obj.mddate != obj.bkdate or not any_exists(nativepath):
                data = obj.data
                if obj.type == b'TEXT':
                    data = data.decode('mac_roman').replace('\r', os.linesep).encode('utf8')

                rsrc = obj.rsrc
                if rsrc:
                    rsrc = parse_file(rsrc)
                    rsrc = make_rez_code(rsrc, ascii_clean=True)
                
                info = obj.type + obj.creator
                if info == b'????????': info = b''

                for thing, suffix in ((data, ''), (rsrc, '.rdump'), (info, '.idump')):
                    wholepath = nativepath + suffix
                    if thing or (suffix == '' and not rsrc):
                        written.append(wholepath)
                        with open(written[-1], 'wb') as f:
                            f.write(thing)
                    else:
                        try:
                            os.remove(wholepath)
                        except FileNotFoundError:
                            pass

        if written:
            t = path.getmtime(written[-1])
            for w in written:
                os.utime(w, (t, t))


class Folder(AbstractFolder):
    def __init__(self):
        super().__init__()

        self.flags = 0 # help me!
        self.x = 0 # where to put this spatially?
        self.y = 0

        self.crdate = self.mddate = self.bkdate = 0


class File:
    def __init__(self):
        self.type = b'????'
        self.creator = b'????'
        self.flags = 0 # help me!
        self.x = 0 # where to put this spatially?
        self.y = 0

        self.locked = False
        self.crdate = self.mddate = self.bkdate = 0

        self.rsrc = bytearray()
        self.data = bytearray()

    def __str__(self):
        typestr, creatorstr = (x.decode('mac_roman') for x in (self.type, self.creator))
        dstr, rstr = (repr(bytes(x)) if 1 <= len(x) <= 32 else '%db' % len(x) for x in (self.data, self.rsrc))
        return '[%s/%s] data=%s rsrc=%s' % (typestr, creatorstr, dstr, rstr)
