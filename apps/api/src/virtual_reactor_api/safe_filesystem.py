"""Keep platform subprocess decoding failures from aborting research."""
from deepagents.backends import FilesystemBackend

class ResearchFilesystemBackend(FilesystemBackend):
    def _ripgrep_search(self, pattern, base_full, include_glob, max_count=None):
        try:
            return super()._ripgrep_search(pattern,base_full,include_glob,max_count)
        except UnicodeDecodeError:
            # The inherited grep uses its bounded UTF-8 Python search on None.
            # Do not drop undecodable bytes or modify evidence to force a match.
            return None, False
