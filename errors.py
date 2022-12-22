class DistributionNotFound(Exception):
    def __init__(self, path: str, message: str = "Invalid distibution path") -> None:
        self.path = path
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"{self.message}: '{self.path}'"


class CorruptedRemasterFiles(Exception):
    def __init__(self, path: str, message: str = "Corrupted remaster files") -> None:
        self.path = path
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"{self.message}: '{self.path}'"


class FileLoggingSetupError(Exception):
    def __init__(self, path: str, message: str = "Couldn't setup file logging") -> None:
        self.path = path
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"{self.message}: '{self.path}'"


class WrongGameDirectoryPath(Exception):
    pass


class DXRenderDllNotFound(Exception):
    pass


class ExeNotFound(Exception):
    pass


class PatchedButDoesntHaveManifest(Exception):
    def __init__(self, exe_version: str) -> None:
        self.exe_version = exe_version
        super().__init__(self.exe_version)


class ExeNotSupported(Exception):
    def __init__(self, exe_version: str) -> None:
        self.exe_version = exe_version
        super().__init__(self.exe_version)


class ExeIsRunning(Exception):
    pass


class ModsDirMissing(Exception):
    pass


class NoModsFound(Exception):
    pass


class HasManifestButUnpatched(Exception):
    def __init__(self, exe_version: str, manifest_content: str) -> None:
        self.exe_version = exe_version
        self.manifest_content = manifest_content
        super().__init__(self.exe_version)


class InvalidGameDirectory(Exception):
    def __init__(self, missing_path: str) -> None:
        self.missing_path = missing_path
        super().__init__(self.missing_path)


class InvalidExistingManifest(Exception):
    def __init__(self, manifest_path: str) -> None:
        self.manifest_path = manifest_path
        super().__init__(self.manifest_path)
