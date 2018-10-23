import collections


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
