#!/usr/bin/env python3
"""
CAM Topography Regeneration Script - Python Conversion

J. Fyke: call topography-updating routine for CAM
M. Lofverstrom: updates and enhancements
Python Conversion: Following comprehensive conversion plan

This script updates FV1-degree CAM topography in response to 5-km resolution 
Greenland CISM geometry changes prior to the next runstep.
"""

import os
import sys
import subprocess
import shutil
import logging
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from contextlib import contextmanager
import netCDF4
import tempfile


# ============================================================================
# Configuration Classes
# ============================================================================

@dataclass
class TopoConfig:
    """Configuration for topography processing"""
    scratch_run: Path
    use_topo_dataset_as_default: bool = True
    use_spec_topo_dataset: bool = False
    spec_topo_dataset_filename: str = ""
    high_res_dataset: str = "gmted2010"  # or "usgs"
    test_topo_regen: bool = False
    
    # Derived paths (set during initialization)
    ism_topo_file: Optional[Path] = field(init=False, default=None)
    cam_restart_file: Optional[Path] = field(init=False, default=None)
    working_directory: Optional[Path] = field(init=False, default=None)
    data_directory: Optional[Path] = field(init=False, default=None)
    
    # Grid-specific configurations
    grid: Optional[str] = field(init=False, default=None)
    grid_file: Optional[str] = field(init=False, default=None)
    gland_mask_file: Optional[Path] = field(init=False, default=None)
    topo_dataset_def: Optional[Path] = field(init=False, default=None)
    
    def __post_init__(self):
        """Initialize derived paths"""
        self.scratch_run = Path(self.scratch_run)
        self.data_directory = Path("/glade/derecho/scratch/katec/regrid_topo_data")


# ============================================================================
# Custom Exceptions
# ============================================================================

class TopoProcessingError(Exception):
    """Base exception for topography processing"""
    pass

class ValidationError(TopoProcessingError):
    """Input validation failures"""
    pass

class ProcessingStageError(TopoProcessingError):
    """Errors during processing stages"""
    pass

class EnvironmentError(TopoProcessingError):
    """Environment setup failures"""
    pass


# ============================================================================
# Logging Setup
# ============================================================================

def setup_logging(level=logging.INFO) -> logging.Logger:
    """Setup comprehensive logging"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('cam_topo_regen.log')
        ]
    )
    return logging.getLogger(__name__)


# ============================================================================
# Environment Manager
# ============================================================================

class EnvironmentManager:
    """Manages HPC environment setup"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.original_env = os.environ.copy()
        
    def setup_environment(self) -> None:
        """Complete environment setup for the workflow"""
        self.logger.info("Setting up HPC environment...")
        
        try:
            # Source Lmod initialization
            self._source_lmod_init()
            
            # Load required modules
            self._load_modules(['nco', 'ncl/6.6.2', 'conda'])
            
            # Activate conda environment
            self._activate_conda_env('npl')
            
            self.logger.info("Environment setup completed successfully")
            
        except Exception as e:
            raise EnvironmentError(f"Failed to setup environment: {e}")
    
    def _source_lmod_init(self):
        """Source Lmod initialization scripts"""
        lmod_init = "/glade/u/apps/ch/opt/Lmod/7.3.14/lmod/7.3.14/init/bash"
        profile_modules = "/etc/profile.d/modules.sh"
        
        # Note: In practice, these would need to be sourced in the shell
        # For Python, we assume the environment is already set up
        self.logger.debug("Lmod initialization scripts noted for shell setup")
    
    def _load_modules(self, modules: List[str]):
        """Load required modules via Lmod"""
        for module in modules:
            try:
                result = subprocess.run(
                    ['module', 'load', module],
                    capture_output=True, text=True, check=True
                )
                self.logger.debug(f"Loaded module: {module}")
            except subprocess.CalledProcessError as e:
                self.logger.warning(f"Failed to load module {module}: {e}")
    
    def _activate_conda_env(self, env_name: str):
        """Activate conda environment"""
        try:
            # In practice, this would be done via shell activation
            # For Python script, we assume conda env is already active
            self.logger.debug(f"Conda environment {env_name} activation noted")
        except Exception as e:
            self.logger.warning(f"Failed to activate conda env {env_name}: {e}")


# ============================================================================
# File Manager
# ============================================================================

class FileManager:
    """Handles all file operations"""
    
    def __init__(self, config: TopoConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        
    def find_latest_restart_file(self, pattern: str) -> Path:
        """Replace: ls -t $ScratchRun/*.cism.r.* | head -n 1"""
        files = list(self.config.scratch_run.glob(pattern))
        if not files:
            raise ValidationError(f"No files found matching pattern: {pattern}")
        
        latest = max(files, key=lambda f: f.stat().st_mtime)
        self.logger.info(f"Found latest file: {latest}")
        return latest
    
    def create_symlink_safe(self, source: Path, target: Path):
        """Replace: ln -sfv"""
        # Create parent directory if it doesn't exist
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # Remove existing symlink or file
        if target.exists() or target.is_symlink():
            target.unlink()
        
        # Create symlink
        target.symlink_to(source)
        self.logger.debug(f"Created symlink: {target} -> {source}")
    
    def check_netcdf_dimensions(self, filepath: Path) -> Dict[str, int]:
        """Replace: ncdump -h file | grep 'x0 = 300'"""
        try:
            with netCDF4.Dataset(filepath, 'r') as ds:
                dimensions = {name: dim.size for name, dim in ds.dimensions.items()}
                self.logger.debug(f"NetCDF dimensions for {filepath}: {dimensions}")
                return dimensions
        except Exception as e:
            raise ValidationError(f"Failed to read NetCDF dimensions from {filepath}: {e}")
    
    def setup_file_paths(self):
        """Setup and validate all file paths"""
        if self.config.test_topo_regen:
            self.logger.warning("WARNING: USING PATHS TO TOPOGRAPHY REGENERATION TEST FILES!")
            self._setup_test_paths()
        else:
            self.logger.info("Defining I/O files for coupled run topography regeneration")
            self._setup_production_paths()
            
        self._validate_file_existence()
        
    def _setup_test_paths(self):
        """Setup test file paths"""
        test_dir = self.config.scratch_run / "temp_io_files" / "4km_ISM"
        self.config.ism_topo_file = test_dir / "BG_MG1_CISM2.cism.r.0010-01-01-00000.nc"
        self.config.cam_restart_file = test_dir / "BG_MG1_CISM2.cam.r.0010-01-01-00000.nc"
        self.config.working_directory = self.config.scratch_run
        
    def _setup_production_paths(self):
        """Setup production file paths"""
        self.config.ism_topo_file = self.find_latest_restart_file("*.cism.r.*")
        self.config.cam_restart_file = self.find_latest_restart_file("*.cam.r.*")
        self.config.working_directory = self.config.scratch_run / "dynamic_atm_topog"
        
    def _validate_file_existence(self):
        """Validate that required files exist"""
        files_to_check = [
            self.config.ism_topo_file,
            self.config.cam_restart_file
        ]
        
        for file_path in files_to_check:
            if not file_path.exists():
                raise ValidationError(f"Required file does not exist: {file_path}")
            if file_path.stat().st_size == 0:
                raise ValidationError(f"File is empty: {file_path}")
                
        # Check directories
        for dir_path in [self.config.working_directory, self.config.data_directory]:
            if not dir_path.exists():
                raise ValidationError(f"Required directory does not exist: {dir_path}")
                
        self.logger.info("File existence validation completed successfully")


# ============================================================================
# Process Executor
# ============================================================================

class ProcessExecutor:
    """Handles external process execution"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        
    def run_command(self, cmd: List[str], cwd: Optional[Path] = None, 
                   check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
        """Unified command execution with logging and error handling"""
        cmd_str = ' '.join(str(c) for c in cmd)
        self.logger.info(f"Executing: {cmd_str}")
        
        try:
            result = subprocess.run(
                cmd, cwd=cwd, check=check, 
                capture_output=capture, text=True
            )
            
            if capture:
                self.logger.debug(f"Command output: {result.stdout}")
                if result.stderr:
                    self.logger.warning(f"Command stderr: {result.stderr}")
                    
            return result
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Command failed: {cmd_str}"
            if capture and e.stderr:
                error_msg += f"\nError: {e.stderr}"
            raise ProcessingStageError(error_msg)
    
    def run_ncl_script(self, script: str, variables: Dict[str, str], cwd: Path):
        """Handle NCL script execution with variable passing"""
        cmd = ['ncl']
        for key, value in variables.items():
            cmd.append(f'{key}="{value}"')
        cmd.append(script)
        
        return self.run_command(cmd, cwd=cwd)
    
    def run_fortran_executable(self, executable: str, cwd: Path):
        """Handle FORTRAN program execution"""
        return self.run_command([f'./{executable}'], cwd=cwd)


# ============================================================================
# Grid Configuration Manager
# ============================================================================

class GridConfigManager:
    """Manages grid-specific configurations"""
    
    def __init__(self, config: TopoConfig, file_manager: FileManager, logger: logging.Logger):
        self.config = config
        self.file_manager = file_manager
        self.logger = logger
        
    def detect_and_setup_grids(self):
        """Detect grid resolutions and setup grid-specific configurations"""
        self._detect_cism_grid()
        self._detect_cam_grid()
        self._setup_grid_specific_files()
        
    def _detect_cism_grid(self):
        """Detect CISM grid resolution and setup corresponding files"""
        dims = self.file_manager.check_netcdf_dimensions(self.config.ism_topo_file)
        
        regrid_dir = self.config.working_directory / "regridding"
        
        if dims.get('x0') == 300 and dims.get('y0') == 560:
            self.logger.info("CISM topography input APPEARS to be on a 5km CISM grid")
            self._setup_cism_5km_files(regrid_dir)
            
        elif dims.get('x0') == 375 and dims.get('y0') == 700:
            self.logger.info("CISM topography input APPEARS to be on a 4km CISM grid")
            self._setup_cism_4km_files(regrid_dir)
            
        elif dims.get('x1') == 393 and dims.get('y1') == 695:
            self.logger.info("CISM topography input APPEARS to be on a 4km CISM grid (version from 2016-12-19)")
            self._setup_cism_4km_2016_files(regrid_dir)
            
        elif dims.get('x1') == 416 and dims.get('y1') == 704:
            self.logger.info("CISM topography input APPEARS to be on a 4km CISM grid (version from 2017-04-29)")
            self._setup_cism_4km_2017_files(regrid_dir)
            
        else:
            raise ValidationError("CISM topography input appears to be of an incompatible resolution")
    
    def _setup_cism_5km_files(self, regrid_dir: Path):
        """Setup 5km CISM grid files"""
        data_dir = self.config.data_directory
        self.file_manager.create_symlink_safe(
            data_dir / "CISM1_5km_SCRIP_file.nc",
            regrid_dir / "source_grid_file.nc"
        )
        self.file_manager.create_symlink_safe(
            data_dir / "CISM1_5km_weights_file.nc",
            regrid_dir / "weights_file.nc"
        )
        self.file_manager.create_symlink_safe(
            data_dir / "CISM1_5km_lat_lon.nc",
            regrid_dir / "icesheet_lat_lon.nc"
        )
    
    def _setup_cism_4km_files(self, regrid_dir: Path):
        """Setup 4km CISM grid files"""
        data_dir = self.config.data_directory
        self.file_manager.create_symlink_safe(
            data_dir / "CISM2_4km_SCRIP_file.nc",
            regrid_dir / "source_grid_file.nc"
        )
        self.file_manager.create_symlink_safe(
            data_dir / "CISM2_4km_weights_file.nc",
            regrid_dir / "weights_file.nc"
        )
        self.file_manager.create_symlink_safe(
            data_dir / "CISM2_4km_lat_lon.nc",
            regrid_dir / "icesheet_lat_lon.nc"
        )
    
    def _setup_cism_4km_2016_files(self, regrid_dir: Path):
        """Setup 4km CISM grid files (2016 version)"""
        data_dir = self.config.data_directory
        self.file_manager.create_symlink_safe(
            data_dir / "CISM2_4km_2016_12_19_SCRIP_file.nc",
            regrid_dir / "source_grid_file.nc"
        )
        self.file_manager.create_symlink_safe(
            data_dir / "CISM2_4km_2016_12_19_weights_file.nc",
            regrid_dir / "weights_file.nc"
        )
        self.file_manager.create_symlink_safe(
            data_dir / "CISM2_4km_2016_12_19_lat_lon.nc",
            regrid_dir / "icesheet_lat_lon.nc"
        )
    
    def _setup_cism_4km_2017_files(self, regrid_dir: Path):
        """Setup 4km CISM grid files (2017 version)"""
        data_dir = self.config.data_directory
        self.file_manager.create_symlink_safe(
            data_dir / "CISM2_4km_2017_04_29_SCRIP_file.nc",
            regrid_dir / "source_grid_file.nc"
        )
        self.file_manager.create_symlink_safe(
            data_dir / "CISM2_4km_2017_04_29_weights_file.nc",
            regrid_dir / "weights_file.nc"
        )
        self.file_manager.create_symlink_safe(
            data_dir / "CISM2_4km_2017_08_04_lat_lon.nc",
            regrid_dir / "icesheet_lat_lon.nc"
        )
    
    def _detect_cam_grid(self):
        """Detect CAM grid resolution"""
        dims = self.file_manager.check_netcdf_dimensions(self.config.cam_restart_file)
        
        if dims.get('lon') == 288 and dims.get('lat') == 192:
            self.logger.info("CAM data APPEARS to be on a FV1 CESM grid")
            self._setup_fv1_grid()
            
        elif dims.get('lon') == 144 and dims.get('lat') == 96:
            self.logger.info("CAM data APPEARS to be on a FV2 CESM grid")
            self._setup_fv2_grid()
            
        else:
            raise ValidationError("CAM restart appears to be of an incompatible resolution")
    
    def _setup_fv1_grid(self):
        """Setup FV1 grid configuration"""
        self.config.grid = "fv_0.9x1.25"
        self.config.grid_file = f"{self.config.grid}.nc"
        self.config.gland_mask_file = self.config.data_directory / "greenland_mask_FV1.nc"
        
        if self.config.use_topo_dataset_as_default:
            self.config.topo_dataset_def = self.config.scratch_run / "topoDataset.nc"
        elif self.config.use_spec_topo_dataset:
            self.config.topo_dataset_def = Path(self.config.spec_topo_dataset_filename)
        else:
            self.config.topo_dataset_def = self.config.data_directory / "fv_0.9x1.25_topo_c170415.nc"
            
        self.logger.info(f"Using {self.config.topo_dataset_def} as the default background dataset")
    
    def _setup_fv2_grid(self):
        """Setup FV2 grid configuration"""
        self.config.grid = "fv_1.9x2.5"
        self.config.grid_file = f"{self.config.grid}.nc"
        self.config.gland_mask_file = self.config.data_directory / "greenland_mask_FV2.nc"
        
        if self.config.use_topo_dataset_as_default:
            self.config.topo_dataset_def = self.config.scratch_run / "topoDataset.nc"
        elif self.config.use_spec_topo_dataset:
            self.config.topo_dataset_def = Path(self.config.spec_topo_dataset_filename)
        else:
            self.config.topo_dataset_def = self.config.data_directory / "fv_1.9x2.5_topo_c061116.nc"
            
        self.logger.info(f"Using {self.config.topo_dataset_def} as the default background dataset")
    
    def _setup_grid_specific_files(self):
        """Setup additional grid-specific files"""
        self.logger.info("Restart files are correct resolutions")


# ============================================================================
# Processing Stages
# ============================================================================

class RegridStage:
    """Handles the regridding processing stage"""
    
    def __init__(self, config: TopoConfig, file_manager: FileManager, 
                 executor: ProcessExecutor, logger: logging.Logger):
        self.config = config
        self.file_manager = file_manager
        self.executor = executor
        self.logger = logger
        self.regrid_dir = config.working_directory / "regridding"
        
    def execute(self):
        """Execute the regridding stage"""
        self.logger.info("Regridding model topography onto a lat-lon tile, insert into global dataset")
        
        os.chdir(self.regrid_dir)
        
        self._setup_regrid_files()
        self._preprocess_input_topo()
        self._cleanup_existing_files()
        self._run_regridding()
        self._merge_with_global_topo()
        
    def _setup_regrid_files(self):
        """Set up symbolic links and input files"""
        data_dir = self.config.data_directory
        
        # Setup high-resolution dataset
        if self.config.high_res_dataset == "gmted2010":
            source_file = data_dir / "gmted2010_modis-rawdata.nc"
        else:
            source_file = data_dir / "usgs-rawdata.nc"
            
        self.file_manager.create_symlink_safe(
            source_file,
            self.regrid_dir / "highRes-rawdata.nc"
        )
        
        # Setup diagnostic files
        self.file_manager.create_symlink_safe(
            data_dir / "template_out.nc",
            self.regrid_dir / "template_out.nc"
        )
        self.file_manager.create_symlink_safe(
            data_dir / "destination_grid_file.nc",
            self.regrid_dir / "destination_grid_file.nc"
        )
        
    def _preprocess_input_topo(self):
        """Pre-process input topography file"""
        self.logger.info("Creating regridded topography file and merging this into topography")
        
        # Replace: ncwa -O -a time -v thk,topg $ISM_Topo_File input_topography_file.nc
        self.executor.run_command([
            'ncwa', '-O', '-a', 'time', '-v', 'thk,topg',
            str(self.config.ism_topo_file), 'input_topography_file.nc'
        ], cwd=self.regrid_dir)
        
        # Replace: ncks -A -v lat,lon icesheet_lat_lon.nc input_topography_file.nc
        self.executor.run_command([
            'ncks', '-A', '-v', 'lat,lon',
            'icesheet_lat_lon.nc', 'input_topography_file.nc'
        ], cwd=self.regrid_dir)
        
    def _cleanup_existing_files(self):
        """Remove existing files if they exist"""
        files_to_remove = [
            'ISM30sec.archived.nc',
            'modified-highRes.nc',
            'regridded-tile.nc'
        ]
        
        for filename in files_to_remove:
            file_path = self.regrid_dir / filename
            if file_path.exists():
                file_path.unlink()
                self.logger.debug(f"Removed existing file: {filename}")
        
        # Copy original global topography dataset
        shutil.copy2(
            self.regrid_dir / "highRes-rawdata.nc",
            self.regrid_dir / "modified-highRes.nc"
        )
        
    def _run_regridding(self):
        """Execute NCL regrid script"""
        variables = {
            'input_file_name': 'input_topography_file.nc',
            'global_file_name': 'modified-highRes.nc',
            'output_file_name': 'regridded-tile.nc'
        }
        
        try:
            self.executor.run_ncl_script('regrid.ncl', variables, self.regrid_dir)
        except ProcessingStageError:
            raise ProcessingStageError("Ice sheet regrid FAILED")
            
    def _merge_with_global_topo(self):
        """Execute Python mergeTile.py"""
        try:
            self.executor.run_command([
                'python', 'mergeTile.py',
                'modified-highRes.nc', 'regridded-tile.nc'
            ], cwd=self.regrid_dir)
        except ProcessingStageError:
            raise ProcessingStageError("MergeTile.py FAILED")


class BinToCubeStage:
    """Handles the bin_to_cube processing stage"""
    
    def __init__(self, config: TopoConfig, file_manager: FileManager,
                 executor: ProcessExecutor, logger: logging.Logger):
        self.config = config
        self.file_manager = file_manager
        self.executor = executor
        self.logger = logger
        self.stage_dir = config.working_directory / "bin_to_cube"
        
    def execute(self):
        """Execute the bin_to_cube stage"""
        self.logger.info("Running bin_to_cube generator...")
        
        os.chdir(self.stage_dir)
        
        self._setup_stage_files()
        self._generate_namelist()
        self._run_bin_to_cube()
        
    def _setup_stage_files(self):
        """Setup required files for this stage"""
        self.file_manager.create_symlink_safe(
            self.config.data_directory / "landm_coslat.nc",
            self.stage_dir / "landm_coslat.nc"
        )
        
    def _generate_namelist(self):
        """Generate bin_to_cube.nl namelist file"""
        regrid_output = self.config.working_directory / "regridding" / "modified-highRes.nc"
        
        namelist_content = f"""&binparams
  raw_latlon_data_file = '{regrid_output}'
  output_file = 'ncube3000.nc'
  ncube=3000
/
"""
        
        namelist_path = self.stage_dir / "bin_to_cube.nl"
        with open(namelist_path, 'w') as f:
            f.write(namelist_content)
            
        self.logger.debug(f"Generated namelist: {namelist_path}")
        
    def _run_bin_to_cube(self):
        """Run bin_to_cube FORTRAN executable"""
        self.logger.info("Running bin_to_cube...")
        
        try:
            self.executor.run_fortran_executable('bin_to_cube', self.stage_dir)
        except ProcessingStageError:
            raise ProcessingStageError("Bin_to_cube FAILED")


class CubeToTargetStage:
    """Handles the complex cube_to_target processing stage"""
    
    def __init__(self, config: TopoConfig, file_manager: FileManager,
                 executor: ProcessExecutor, logger: logging.Logger):
        self.config = config
        self.file_manager = file_manager
        self.executor = executor
        self.logger = logger
        self.stage_dir = config.working_directory / "cube_to_target"
        
    def execute(self):
        """Execute the cube_to_target stage with all phases"""
        self.logger.info("Running cube_to_target SGH/SGH30 generator...")
        
        os.chdir(self.stage_dir)
        
        self._generate_base_namelist()
        self._run_phase_1a()  # Coarse smoothing
        self._run_phase_1b()  # Ridge finding
        self._run_phase_2a()  # Fine smoothing
        self._run_phase_2b()  # Final mapping
        
    def _generate_base_namelist(self):
        """Generate base namelist configuration"""
        cube_input = self.config.working_directory / "bin_to_cube" / "ncube3000.nc"
        grid_file = self.config.data_directory / self.config.grid_file
        
        if self.config.grid == "fv_0.9x1.25":
            params = {
                'ncube_sph_smooth_coarse': 60,
                'nwindow_halfwidth': 42,
                'nridge_subsample': 8
            }
        else:  # fv_1.9x2.5
            params = {
                'ncube_sph_smooth_coarse': 120,
                'nwindow_halfwidth': 84,
                'nridge_subsample': 16
            }
            
        self.base_namelist = f"""  &topoparams
    grid_descriptor_fname           = '{grid_file}'
    output_grid                     = '{self.config.grid}'
    intermediate_cubed_sphere_fname = '{cube_input}'
    output_fname                    = 'junk'
    externally_smoothed_topo_file   = 'junk'
    lsmooth_terr = .false.
    lexternal_smooth_terr = .false.
    lzero_out_ocean_point_phis = .false.
    lzero_negative_peaks = .true.
    lsmooth_on_cubed_sphere = .true.
    ncube_sph_smooth_coarse = {params['ncube_sph_smooth_coarse']}
    ncube_sph_smooth_fine = 1
    ncube_sph_smooth_iter = 1
    lfind_ridges = .true.
    lridgetiles = .false.
    nwindow_halfwidth = {params['nwindow_halfwidth']}
    nridge_subsample = {params['nridge_subsample']}
    lread_smooth_topofile = .true.
  /
"""
        
    def _write_namelist(self, content: str):
        """Write namelist content to file"""
        with open(self.stage_dir / "cube_to_target.nl", 'w') as f:
            f.write(content)
            
    def _modify_namelist_parameter(self, content: str, param: str, new_value: str) -> str:
        """Modify a specific parameter in the namelist"""
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if param in line and '=' in line:
                # Replace the value after the equals sign
                parts = line.split('=')
                lines[i] = f"{parts[0]}= {new_value}"
                break
        return '\n'.join(lines)
    
    def _run_phase_1a(self):
        """Phase 1a: smooth topo w/ coarse smoother"""
        self.logger.info("Running cube_to_target phase 1a...")
        
        # Modify namelist: set lread_smooth_topofile = .false.
        namelist = self._modify_namelist_parameter(
            self.base_namelist, 'lread_smooth_topofile', '.false.'
        )
        self._write_namelist(namelist)
        
        try:
            self.executor.run_fortran_executable('cube_to_target', self.stage_dir)
        except ProcessingStageError:
            raise ProcessingStageError("Cube_to_target phase 1a FAILED")
    
    def _run_phase_1b(self):
        """Phase 1b: find ridges and map to FV model grid"""
        self.logger.info("Running cube_to_target phase 1b...")
        
        # Modify namelist: set lread_smooth_topofile = .true.
        namelist = self._modify_namelist_parameter(
            self.base_namelist, 'lread_smooth_topofile', '.true.'
        )
        self._write_namelist(namelist)
        
        try:
            self.executor.run_fortran_executable('cube_to_target', self.stage_dir)
        except ProcessingStageError:
            raise ProcessingStageError("Cube_to_target phase 1b FAILED")
    
    def _run_phase_2a(self):
        """Phase 2a: smooth topo w/ fine smoother for Greenland SGH30 adjustment"""
        self.logger.info("Running cube_to_target phase 2a...")
        
        # Start with base namelist and modify for phase 2a
        namelist = self._modify_namelist_parameter(
            self.base_namelist, 'lread_smooth_topofile', '.false.'
        )
        
        # Change coarse smoothing parameter
        if self.config.grid == "fv_0.9x1.25":
            new_coarse = "8"
        else:  # fv_1.9x2.5
            new_coarse = "16"
            
        namelist = self._modify_namelist_parameter(
            namelist, 'ncube_sph_smooth_coarse', new_coarse
        )
        self._write_namelist(namelist)
        
        try:
            self.executor.run_fortran_executable('cube_to_target', self.stage_dir)
        except ProcessingStageError:
            raise ProcessingStageError("Cube_to_target phase 2a FAILED")
    
    def _run_phase_2b(self):
        """Phase 2b: skip ridges but map to FV model grid"""
        self.logger.info("Running cube_to_target phase 2b...")
        
        # Start with phase 2a configuration
        namelist = self._modify_namelist_parameter(
            self.base_namelist, 'lread_smooth_topofile', '.true.'
        )
        
        # Change coarse smoothing parameter
        if self.config.grid == "fv_0.9x1.25":
            new_coarse = "8"
        else:  # fv_1.9x2.5
            new_coarse = "16"
            
        namelist = self._modify_namelist_parameter(
            namelist, 'ncube_sph_smooth_coarse', new_coarse
        )
        
        # Skip ridge finding
        namelist = self._modify_namelist_parameter(
            namelist, 'lfind_ridges', '.false.'
        )
        self._write_namelist(namelist)
        
        try:
            self.executor.run_fortran_executable('cube_to_target', self.stage_dir)
        except ProcessingStageError:
            raise ProcessingStageError("Cube_to_target phase 2b FAILED")


class PostProcessStage:
    """Handles the post-processing stage"""
    
    def __init__(self, config: TopoConfig, file_manager: FileManager,
                 executor: ProcessExecutor, logger: logging.Logger):
        self.config = config
        self.file_manager = file_manager
        self.executor = executor
        self.logger = logger
        self.stage_dir = config.working_directory / "postproc"
        
    def execute(self):
        """Execute the post-processing stage"""
        self.logger.info("Merging datasets...")
        
        os.chdir(self.stage_dir)
        
        self._setup_output_dataset()
        self._get_cube_to_target_outputs()
        self._run_postprocessing()
        
    def _setup_output_dataset(self):
        """Setup the output topography dataset"""
        topo_dataset = self.config.scratch_run / "topoDataset.nc"
        
        # Copy the default dataset to the output location
        shutil.copy2(self.config.topo_dataset_def, topo_dataset)
        
        # Make it writable
        topo_dataset.chmod(0o644)
        
        self.topo_dataset = topo_dataset
        
    def _get_cube_to_target_outputs(self):
        """Get the cube_to_target output file paths"""
        c2t_output_dir = self.config.working_directory / "cube_to_target" / "output"
        
        if self.config.grid == "fv_0.9x1.25":
            self.c2t060 = c2t_output_dir / f"{self.config.grid}_nc3000_Nsw042_Nrs008_Co060_Fi001.nc"
            self.c2t008 = c2t_output_dir / f"{self.config.grid}_nc3000_NoAniso_Co008_Fi001.nc"
        else:  # fv_1.9x2.5
            self.c2t060 = c2t_output_dir / f"{self.config.grid}_nc3000_Nsw084_Nrs016_Co120_Fi001.nc"
            self.c2t008 = c2t_output_dir / f"{self.config.grid}_nc3000_NoAniso_Co016_Fi001.nc"
            
    def _run_postprocessing(self):
        """Run the Python post-processing script"""
        try:
            self.executor.run_command([
                'python', 'postproc_mask.py',
                str(self.config.cam_restart_file),
                str(self.topo_dataset),
                str(self.config.gland_mask_file),
                str(self.c2t060),
                str(self.c2t008)
            ], cwd=self.stage_dir)
        except ProcessingStageError:
            raise ProcessingStageError("Python postproc_mask FAILED")


# ============================================================================
# Main Topography Processor
# ============================================================================

class TopographyProcessor:
    """Main class that orchestrates the entire topography processing workflow"""
    
    def __init__(self, config: TopoConfig):
        self.config = config
        self.logger = setup_logging()
        
        # Initialize managers
        self.env_manager = EnvironmentManager(self.logger)
        self.file_manager = FileManager(config, self.logger)
        self.executor = ProcessExecutor(self.logger)
        self.grid_manager = GridConfigManager(config, self.file_manager, self.logger)
        
        # Initialize processing stages
        self.regrid_stage = RegridStage(config, self.file_manager, self.executor, self.logger)
        self.bin_to_cube_stage = BinToCubeStage(config, self.file_manager, self.executor, self.logger)
        self.cube_to_target_stage = CubeToTargetStage(config, self.file_manager, self.executor, self.logger)
        self.postproc_stage = PostProcessStage(config, self.file_manager, self.executor, self.logger)
        
    def run(self):
        """Execute the complete topography processing workflow"""
        try:
            self.logger.info("****Running CAM topography-updating routine...****")
            
            # Phase 1: Setup and validation
            self.logger.info("-> Setting location of necessary input/output files and directories")
            self._setup_and_validate()
            
            # Phase 2: Processing stages
            os.chdir(self.config.working_directory)
            
            self.regrid_stage.execute()
            self.bin_to_cube_stage.execute()
            self.cube_to_target_stage.execute()
            self.postproc_stage.execute()
            
            # Phase 3: Completion
            self.logger.info("")
            self.logger.info("-> Topography updating finished successfully")
            self.logger.info("-> Returning to working directory")
            os.chdir(self.config.working_directory)
            
            return 0
            
        except Exception as e:
            self.logger.error(f"Topography processing failed: {e}")
            return 1
    
    def _setup_and_validate(self):
        """Setup environment and validate all inputs"""
        # Setup HPC environment
        self.env_manager.setup_environment()
        
        # Setup and validate file paths
        self.file_manager.setup_file_paths()
        
        # Print file information
        self.logger.info(f"Input CISM restart file is {self.config.ism_topo_file}")
        self.logger.info(f"CAM restart file (only used for an array size check) is {self.config.cam_restart_file}")
        
        # Detect and setup grid configurations
        self.grid_manager.detect_and_setup_grids()
        
        self.logger.info("Success: input/output files exist:")
        self.logger.info(f"Ice sheet topography input file = {self.config.ism_topo_file}")
        self.logger.info(f"CAM restart file = {self.config.cam_restart_file}")


# ============================================================================
# Command Line Interface
# ============================================================================

def create_argument_parser() -> argparse.ArgumentParser:
    """Create command line argument parser"""
    parser = argparse.ArgumentParser(
        description="CAM Topography Regeneration Script - Python Version",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Standard production run
  python cam_topo_regen.py /glade/work/tsegal/test_topoupdater_data

  # Test run with USGS dataset
  python cam_topo_regen.py /path/to/scratch --test --high-res-dataset usgs

  # Use specific background topography
  python cam_topo_regen.py /path/to/scratch --spec-topo-dataset /path/to/custom/topo.nc
        """
    )
    
    parser.add_argument(
        'scratch_run',
        type=Path,
        help='Path to scratch run directory'
    )
    
    parser.add_argument(
        '--test', 
        action='store_true',
        help='Use test topography regeneration files'
    )
    
    parser.add_argument(
        '--high-res-dataset',
        choices=['gmted2010', 'usgs'],
        default='gmted2010',
        help='High resolution topography dataset to use (default: gmted2010)'
    )
    
    parser.add_argument(
        '--use-default-topo',
        action='store_true',
        default=True,
        help='Use topoDataset.nc from run directory as background (default: True)'
    )
    
    parser.add_argument(
        '--spec-topo-dataset',
        type=str,
        help='Path to specific background topography dataset file'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate inputs but do not run processing'
    )
    
    return parser


def main():
    """Main entry point"""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Setup logging level
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logging(log_level)
    
    try:
        # Create configuration
        config = TopoConfig(
            scratch_run=args.scratch_run,
            test_topo_regen=args.test,
            high_res_dataset=args.high_res_dataset,
            use_topo_dataset_as_default=args.use_default_topo,
            use_spec_topo_dataset=bool(args.spec_topo_dataset),
            spec_topo_dataset_filename=args.spec_topo_dataset or ""
        )
        
        # Validate scratch run directory exists
        if not config.scratch_run.exists():
            raise ValidationError(f"Scratch run directory does not exist: {config.scratch_run}")
        
        logger.info(f"Configuration: {config}")
        
        if args.dry_run:
            logger.info("Dry run mode - validating inputs only")
            processor = TopographyProcessor(config)
            processor._setup_and_validate()
            logger.info("Validation completed successfully")
            return 0
        
        # Run the processor
        processor = TopographyProcessor(config)
        return processor.run()
        
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
