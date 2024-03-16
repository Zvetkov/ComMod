class DistributionNotFoundError(Exception):
    def __init__(self, path: str, message: str = "Invalid distibution path") -> None:
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


class WrongGameDirectoryPathError(Exception):
    pass


class DXRenderDllNotFoundError(Exception):
    pass


class ExeNotFoundError(Exception):
    pass


class PatchedButDoesntHaveManifestError(Exception):
    def __init__(self, exe_version: str) -> None:
        self.exe_version = exe_version
        super().__init__(self.exe_version)


class ExeNotSupportedError(Exception):
    def __init__(self, exe_version: str) -> None:
        self.exe_version = exe_version
        super().__init__(self.exe_version)


class ExeIsRunningError(Exception):
    pass


class ModsDirMissingError(Exception):
    pass


class NoModsFoundError(Exception):
    pass


class HasManifestButUnpatchedError(Exception):
    def __init__(self, exe_version: str, manifest_content: str) -> None:
        self.exe_version = exe_version
        self.manifest_content = manifest_content
        super().__init__(self.exe_version)


class InvalidGameDirectoryError(Exception):
    def __init__(self, missing_path: str) -> None:
        self.missing_path = missing_path
        super().__init__(self.missing_path)

    def __str__(self) -> str:
        return f"Path is missing: '{self.missing_path}'"


class InvalidExistingManifestError(Exception):
    def __init__(self, manifest_path: str) -> None:
        self.manifest_path = manifest_path
        super().__init__(self.manifest_path)

    def __str__(self) -> str:
        return f"Manifest is invalid: '{self.manifest_path}'"
