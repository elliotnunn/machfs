import collections


_CASE = list(range(256)) # cheating, fix this!



def _to_lower(orig):
    return bytes(_CASE[x] for x in orig)


class AbstractFolder(collections.MutableMapping):
    def __init__(self, from_dict=()):
        self._prefdict = {} # lowercase to preferred
        self._maindict = {} # lowercase to contents
        self.update(from_dict)

    def __setitem__(self, key, value):
        try:
            key = key.encode('mac_roman')
        except AttributeError:
            pass

        if len(key) > 31:
            raise ValueError('Max filename length = 31')

        lower = _to_lower(key)
        self._prefdict[lower] = key
        self._maindict[lower] = value

    def __getitem__(self, key):
        try:
            key = key.encode('mac_roman')
        except AttributeError:
            pass

        lower = _to_lower(key)
        return self._maindict[lower]

    def __delitem__(self, key):
        try:
            value = value.encode('mac_roman')
        except AttributeError:
            pass

        lower = _to_lower(key)
        del self._maindict[lower]
        del self._prefdict[lower]

    def __iter__(self):
        return iter(self._prefdict.values())

    def __len__(self):
        return len(self._maindict)

    def __repr__(self):
        the_dict = {self._prefdict[k]: v for (k, v) in self._maindict.items()}
        return repr(the_dict)

    def iter_paths(self):
        for name, child in self.items():
            print(name, child)
            yield ((name,), child)
            try:
                childs_children = child.iter_paths()
            except AttributeError:
                pass
            else:
                for each_path, each_child in childs_children:
                    yield (name,) + each_path, each_child
