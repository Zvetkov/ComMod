from pathlib import Path
from aiopath import AsyncPath
from zipfile import ZipInfo
from py7zr import py7zr
from mod import Mod

logger = logging.getLogger('dem')

class ModArchive:
    '''Simplified mod structure representing compressed mod before extraction'''
    def __init__(self, manifest: dict,
                 archive_path: str,
                 archive_file_list: list[ZipInfo] | py7zr.ArchiveFileList):
        logger.debug(f"Loading mod archive from path: {archive_path}")
        try:
            Mod.validate_install_config_struct(manifest)
        except Exception as ex:
            a = 1

    def validate_archive_mod_paths(
            self, mod_config_path, archive_file_list: list[ZipInfo] | py7zr.ArchiveFileList):
        
        validated = True

        if isinstance(archive_file_list, py7zr.ArchiveFileList):
            archive_files = []
            for file in archive_file_list:
                if file.emptystream:
                    archive_files.append(f"{file.filename}/")
                else:
                    archive_files.append(file.filename)
        elif isinstance(archive_file_list, list[ZipInfo]):
            archive_files = [file.filename for file in archive_file_list]
        else:
            raise NotImplemented("Wrong archive type passed to validator")
        
        if not self.no_base_content:
            mod_base_paths = []
            if self.base_data_dirs:
                # TODO: check that using Path instead of str is not breaking checks here
                mod_base_paths = [Path(mod_config_path).parent / dir for dir in self.base_data_dirs]
            else:
                mod_base_paths.append(Path(mod_config_path).parent / "data")
            
            if self.bin_dirs:
                mod_base_paths.extend(Path(mod_config_path).parent / dir for dir in self.bin_dirs)

            data_dir_validated = all(base_path in archive_files for base_path in mod_base_paths)
            validated &= data_dir_validated
            if data_dir_validated:
                logger.info("\tPASS: Archived base mod data folder validation result")
            else:
                logger.error("\tFAIL: Archived base mod data folder validation fail, "
                             f"expected path not found: {mod_base_paths}")
                
        if not validated:
            logger.info("<! BASE FILES VALIDATION FAILED, SKIPPING FURTHER CHECKS !>")
            return validated
        
        if self.optional_content:
            for option in self.optional_content:
                validated &= mod_config_path.replace(
                    "manifest.yaml", f'{self.options_base_dir}{option.get("name")}/') in archive_files
                if option.get("install_settings") is not None:
                    for setting in option.get("install_settings"):
                        validated &= mod_config_path.replace(
                            "manifest.yaml",
                            f'{option.get("name")}/{setting.get("name")}/data/') in archive_files
                        logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                                    f"Archived optional content '{option.get('name')}' "
                                    f"install setting '{setting.get('name')}' "
                                    f"data folder validation result")
                else:
                    validated &= mod_config_path.replace(
                        "manifest.yaml", f'{option.get("name")}/data/') in archive_files
                logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                            f"Archived optional content '{option.get('name')}' "
                            "data folder validation result")