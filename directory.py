class AbstractFolder(dict):
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
