from pathlib import Path

from commod.localisation.service import tr


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

class ModMissingFileInstallationError(Exception):
    def __init__(self, problematic_file: Path | str) -> None:
        self.problematic_file = problematic_file
        super().__init__(self.problematic_file)

    def __str__(self) -> str:
        return (tr("missing_target_file_for_merge_command",
                  target=str(Path("data") / self.problematic_file))
                + "\n\n" + tr("mod_is_incompatible_with_current_game")
                + "\n\n" + tr("debug_info_is_available"))

class ModInvalidMergeInstallationError(Exception):
    def __init__(self, problematic_file: Path | str, command_str: str | None = None) -> None:
        self.problematic_file = problematic_file
        self.command_str = command_str
        super().__init__(self.problematic_file)

    def __str__(self) -> str:
        return (tr("unable_to_apply_commands",
                  target=str(self.problematic_file))
                + (f"\n{self.command_str}" if self.command_str else "")
                + "\n\n" + tr("mod_is_incompatible_with_current_game")
                + "\n\n" + tr("debug_info_is_available"))

class ModFilePackagingError(Exception):
    pass
