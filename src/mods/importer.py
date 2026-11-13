"""Read Mod source afresh on enable, including relative helper imports.

Python's normal bytecode cache can reuse an old module if an edit has the same
size and timestamp. A developer toggling a Mod should always get its new source.
Only the loader's private package names use this finder; game imports are normal.
"""

from importlib.abc import MetaPathFinder
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_file_location
import sys


class ModSourceLoader(SourceFileLoader):
    def get_code(self, fullname):
        return self.source_to_code(self.get_data(self.path), self.path)


class ModSourceFinder(MetaPathFinder):
    def __init__(self):
        self.roots = {}

    def find_spec(self, fullname, path=None, target=None):
        prefix, separator, relative = fullname.partition(".")
        root = self.roots.get(prefix)
        if root is None or not separator:
            return None
        parts = relative.split(".")
        if not all(part.isidentifier() for part in parts):
            return None
        candidate = root.joinpath(*parts)
        if (candidate / "__init__.py").is_file():
            source = candidate / "__init__.py"
            locations = [str(candidate)]
        elif candidate.with_suffix(".py").is_file():
            source = candidate.with_suffix(".py")
            locations = None
        else:
            return None
        return spec_from_file_location(fullname, source,
                                       loader=ModSourceLoader(fullname, str(source)),
                                       submodule_search_locations=locations)


mod_sources = ModSourceFinder()


def register_source(package, root):
    if mod_sources not in sys.meta_path:
        sys.meta_path.insert(0, mod_sources)
    mod_sources.roots[package] = root
