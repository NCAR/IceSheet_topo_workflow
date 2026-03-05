#!/usr/bin/env python3
"""
Unit Test Suite for CAM Topography Processor
Based on the Testing and Validation Strategy document
"""

import pytest
import tempfile
import shutil
import os
import sys
import subprocess
import json
import numpy as np
import netCDF4
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
from contextlib import contextmanager
import logging

# Import the main modules (assuming they're in the same directory)
sys.path.insert(0, str(Path(__file__).parent))
from postrun_CAM_topo_regen_conversion import (
    TopoConfig, TopographyProcessor, FileManager, EnvironmentManager,
    GridConfigManager, ProcessExecutor, RegridStage, BinToCubeStage,
    CubeToTargetStage, PostProcessStage, ValidationError, 
    ProcessingStageError, EnvironmentError
)


# ============================================================================
# Test Fixtures and Utilities
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_netcdf_file():
    """Create a mock NetCDF file for testing"""
    def _create_mock_file(filepath: Path, dimensions: dict, variables: dict = None):
        """Create a real NetCDF file with specified dimensions and variables"""
        with netCDF4.Dataset(filepath, 'w') as ds:
            # Create dimensions
            for dim_name, dim_size in dimensions.items():
                ds.createDimension(dim_name, dim_size)
            
            # Create variables if specified
            if variables:
                for var_name, var_info in variables.items():
                    var = ds.createVariable(var_name, var_info['dtype'], var_info['dimensions'])
                    if 'data' in var_info:
                        var[:] = var_info['data']
                    # Add attributes
                    for attr_name, attr_value in var_info.get('attributes', {}).items():
                        var.setncattr(attr_name, attr_value)
    
    return _create_mock_file


@pytest.fixture
def sample_config(temp_dir):
    """Create a sample configuration for testing"""
    config = TopoConfig(
        scratch_run=temp_dir / "scratch_run",
        use_topo_dataset_as_default=True,
        high_res_dataset="gmted2010",
        test_topo_regen=False
    )
    
    # Create required directories
    config.scratch_run.mkdir(parents=True, exist_ok=True)
    config.data_directory.mkdir(parents=True, exist_ok=True)
    
    return config


@pytest.fixture
def mock_logger():
    """Create a mock logger for testing"""
    logger = Mock(spec=logging.Logger)
    logger.info = Mock()
    logger.debug = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    return logger


# ============================================================================
# NetCDF Comparison Utilities (from testing strategy)
# ============================================================================

def compare_netcdf_files(file1: Path, file2: Path, tolerance: float = 1e-12) -> dict:
    """Compare two NetCDF files with detailed analysis"""
    
    results = {
        'files_identical': True,
        'dimension_differences': [],
        'variable_differences': [],
        'attribute_differences': [],
        'data_differences': [],
        'max_absolute_difference': 0.0,
        'max_relative_difference': 0.0
    }
    
    try:
        with netCDF4.Dataset(file1, 'r') as ds1, netCDF4.Dataset(file2, 'r') as ds2:
            
            # Compare dimensions
            dims1 = {name: dim.size for name, dim in ds1.dimensions.items()}
            dims2 = {name: dim.size for name, dim in ds2.dimensions.items()}
            
            if dims1 != dims2:
                results['files_identical'] = False
                results['dimension_differences'] = {
                    'file1_only': list(set(dims1.keys()) - set(dims2.keys())),
                    'file2_only': list(set(dims2.keys()) - set(dims1.keys())),
                    'size_differences': {name: (dims1[name], dims2[name]) 
                                       for name in dims1.keys() & dims2.keys() 
                                       if dims1[name] != dims2[name]}
                }
            
            # Compare variables
            vars1 = set(ds1.variables.keys())
            vars2 = set(ds2.variables.keys())
            
            if vars1 != vars2:
                results['files_identical'] = False
                results['variable_differences'] = {
                    'file1_only': list(vars1 - vars2),
                    'file2_only': list(vars2 - vars1)
                }
            
            # Compare data for common variables
            common_vars = vars1 & vars2
            for var_name in common_vars:
                var1 = ds1.variables[var_name]
                var2 = ds2.variables[var_name]
                
                # Compare data
                try:
                    data1 = var1[:]
                    data2 = var2[:]
                    
                    if data1.shape != data2.shape:
                        results['files_identical'] = False
                        results['data_differences'].append({
                            'variable': var_name,
                            'issue': 'shape_mismatch',
                            'shapes': (data1.shape, data2.shape)
                        })
                        continue
                    
                    # Check for exact equality first
                    if np.array_equal(data1, data2, equal_nan=True):
                        continue
                    
                    results['files_identical'] = False
                    
                    # Calculate differences for numeric data
                    if np.issubdtype(data1.dtype, np.number):
                        abs_diff = np.abs(data1 - data2)
                        max_abs_diff = np.nanmax(abs_diff)
                        
                        # Avoid division by zero
                        with np.errstate(divide='ignore', invalid='ignore'):
                            rel_diff = abs_diff / np.abs(data1)
                            max_rel_diff = np.nanmax(rel_diff[np.isfinite(rel_diff)])
                            if not np.isfinite(max_rel_diff):
                                max_rel_diff = 0.0
                        
                        results['max_absolute_difference'] = max(
                            results['max_absolute_difference'], max_abs_diff
                        )
                        results['max_relative_difference'] = max(
                            results['max_relative_difference'], max_rel_diff
                        )
                        
                        if max_abs_diff > tolerance:
                            results['data_differences'].append({
                                'variable': var_name,
                                'max_absolute_difference': float(max_abs_diff),
                                'max_relative_difference': float(max_rel_diff),
                                'num_different_values': int(np.sum(abs_diff > tolerance)),
                                'total_values': int(data1.size)
                            })
                    
                except Exception as e:
                    results['data_differences'].append({
                        'variable': var_name,
                        'issue': 'comparison_error',
                        'error': str(e)
                    })
                    
    except Exception as e:
        results['comparison_error'] = str(e)
        return results
    
    return results


# ============================================================================
# Configuration Tests
# ============================================================================

class TestTopoConfig:
    """Test the TopoConfig dataclass"""
    
    def test_config_initialization(self, temp_dir):
        """Test basic configuration initialization"""
        config = TopoConfig(
            scratch_run=temp_dir,
            use_topo_dataset_as_default=True,
            high_res_dataset="gmted2010"
        )
        
        assert config.scratch_run == temp_dir
        assert config.use_topo_dataset_as_default is True
        assert config.high_res_dataset == "gmted2010"
        assert config.data_directory == Path("/glade/derecho/scratch/katec/regrid_topo_data")
    
    def test_config_defaults(self, temp_dir):
        """Test default configuration values"""
        config = TopoConfig(scratch_run=temp_dir)
        
        assert config.use_topo_dataset_as_default is True
        assert config.use_spec_topo_dataset is False
        assert config.spec_topo_dataset_filename == ""
        assert config.high_res_dataset == "gmted2010"
        assert config.test_topo_regen is False
    
    def test_config_path_conversion(self, temp_dir):
        """Test that string paths are converted to Path objects"""
        config = TopoConfig(scratch_run=str(temp_dir))
        
        assert isinstance(config.scratch_run, Path)
        assert config.scratch_run == temp_dir


# ============================================================================
# File Manager Tests
# ============================================================================

class TestFileManager:
    """Test the FileManager class"""
    
    def test_find_latest_restart_file(self, sample_config, temp_dir, mock_logger):
        """Test finding the latest restart file"""
        file_manager = FileManager(sample_config, mock_logger)
        
        # Create test files with different modification times
        test_files = []
        for i, suffix in enumerate(['0001', '0002', '0003']):
            file_path = sample_config.scratch_run / f"test.cism.r.{suffix}.nc"
            file_path.touch()
            # Set different modification times
            os.utime(file_path, (1000 + i, 1000 + i))
            test_files.append(file_path)
        
        # Find latest file
        latest = file_manager.find_latest_restart_file("*.cism.r.*.nc")
        
        assert latest == test_files[-1]  # Should be the last (newest) file
        mock_logger.info.assert_called()
    
    def test_find_latest_restart_file_no_files(self, sample_config, mock_logger):
        """Test error when no files match pattern"""
        file_manager = FileManager(sample_config, mock_logger)
        
        with pytest.raises(ValidationError, match="No files found matching pattern"):
            file_manager.find_latest_restart_file("*.nonexistent.*")
    
    def test_create_symlink_safe(self, sample_config, temp_dir, mock_logger):
        """Test safe symbolic link creation"""
        file_manager = FileManager(sample_config, mock_logger)
        
        # Create source file
        source = temp_dir / "source.txt"
        source.write_text("test content")
        
        # Create symlink
        target = temp_dir / "subdir" / "target.txt"
        file_manager.create_symlink_safe(source, target)
        
        assert target.is_symlink()
        assert target.resolve() == source
        assert target.read_text() == "test content"
        mock_logger.debug.assert_called()
    
    def test_create_symlink_safe_overwrite(self, sample_config, temp_dir, mock_logger):
        """Test symlink overwrite behavior"""
        file_manager = FileManager(sample_config, mock_logger)
        
        # Create source files
        source1 = temp_dir / "source1.txt"
        source1.write_text("content1")
        source2 = temp_dir / "source2.txt"
        source2.write_text("content2")
        
        # Create initial symlink
        target = temp_dir / "target.txt"
        file_manager.create_symlink_safe(source1, target)
        assert target.read_text() == "content1"
        
        # Overwrite with new symlink
        file_manager.create_symlink_safe(source2, target)
        assert target.read_text() == "content2"
    
    def test_check_netcdf_dimensions(self, sample_config, temp_dir, mock_logger, mock_netcdf_file):
        """Test NetCDF dimension checking"""
        file_manager = FileManager(sample_config, mock_logger)
        
        # Create test NetCDF file
        nc_file = temp_dir / "test.nc"
        mock_netcdf_file(nc_file, {'x0': 300, 'y0': 560, 'time': 1})
        
        dims = file_manager.check_netcdf_dimensions(nc_file)
        
        assert dims == {'x0': 300, 'y0': 560, 'time': 1}
        mock_logger.debug.assert_called()
    
    def test_check_netcdf_dimensions_invalid_file(self, sample_config, temp_dir, mock_logger):
        """Test error handling for invalid NetCDF file"""
        file_manager = FileManager(sample_config, mock_logger)
        
        # Create invalid file
        invalid_file = temp_dir / "invalid.nc"
        invalid_file.write_text("not a netcdf file")
        
        with pytest.raises(ValidationError, match="Failed to read NetCDF dimensions"):
            file_manager.check_netcdf_dimensions(invalid_file)
    
    def test_setup_production_paths(self, sample_config, temp_dir, mock_logger):
        """Test production path setup"""
        file_manager = FileManager(sample_config, mock_logger)
        
        # Create mock restart files
        cism_file = sample_config.scratch_run / "test.cism.r.0001.nc"
        cam_file = sample_config.scratch_run / "test.cam.r.0001.nc"
        cism_file.touch()
        cam_file.touch()
        
        # Create working directory
        working_dir = sample_config.scratch_run / "dynamic_atm_topog"
        working_dir.mkdir(parents=True)
        
        file_manager._setup_production_paths()
        
        assert sample_config.ism_topo_file == cism_file
        assert sample_config.cam_restart_file == cam_file
        assert sample_config.working_directory == working_dir
    
    def test_setup_test_paths(self, sample_config, temp_dir, mock_logger):
        """Test test path setup"""
        file_manager = FileManager(sample_config, mock_logger)
        
        # Create test directory structure
        test_dir = sample_config.scratch_run / "temp_io_files" / "4km_ISM"
        test_dir.mkdir(parents=True)
        
        cism_file = test_dir / "BG_MG1_CISM2.cism.r.0010-01-01-00000.nc"
        cam_file = test_dir / "BG_MG1_CISM2.cam.r.0010-01-01-00000.nc"
        cism_file.touch()
        cam_file.touch()
        
        file_manager._setup_test_paths()
        
        assert sample_config.ism_topo_file == cism_file
        assert sample_config.cam_restart_file == cam_file
        assert sample_config.working_directory == sample_config.scratch_run
    
    def test_validate_file_existence(self, sample_config, temp_dir, mock_logger):
        """Test file existence validation"""
        file_manager = FileManager(sample_config, mock_logger)
        
        # Create required files
        sample_config.ism_topo_file = temp_dir / "cism.nc"
        sample_config.cam_restart_file = temp_dir / "cam.nc"
        sample_config.working_directory = temp_dir / "work"
        
        sample_config.ism_topo_file.write_text("test")
        sample_config.cam_restart_file.write_text("test")
        sample_config.working_directory.mkdir()
        
        # Should not raise exception
        file_manager._validate_file_existence()
        mock_logger.info.assert_called()
    
    def test_validate_file_existence_missing_file(self, sample_config, temp_dir, mock_logger):
        """Test validation failure for missing file"""
        file_manager = FileManager(sample_config, mock_logger)
        
        # Set non-existent file
        sample_config.ism_topo_file = temp_dir / "nonexistent.nc"
        sample_config.cam_restart_file = temp_dir / "cam.nc"
        sample_config.working_directory = temp_dir
        
        with pytest.raises(ValidationError, match="Required file does not exist"):
            file_manager._validate_file_existence()


# ============================================================================
# Process Executor Tests
# ============================================================================

class TestProcessExecutor:
    """Test the ProcessExecutor class"""
    
    def test_run_command_success(self, mock_logger):
        """Test successful command execution"""
        executor = ProcessExecutor(mock_logger)
        
        result = executor.run_command(['echo', 'hello'], capture=True)
        
        assert result.returncode == 0
        assert 'hello' in result.stdout
        mock_logger.info.assert_called()
    
    def test_run_command_failure(self, mock_logger):
        """Test command execution failure"""
        executor = ProcessExecutor(mock_logger)
        
        with pytest.raises(ProcessingStageError, match="Command failed"):
            executor.run_command(['false'], check=True)
    
    def test_run_command_no_check(self, mock_logger):
        """Test command execution without check"""
        executor = ProcessExecutor(mock_logger)
        
        result = executor.run_command(['false'], check=False)
        
        assert result.returncode != 0
        # Should not raise exception
    
    def test_run_ncl_script(self, mock_logger):
        """Test NCL script execution"""
        executor = ProcessExecutor(mock_logger)
        
        with patch.object(executor, 'run_command') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            
            variables = {'var1': 'value1', 'var2': 'value2'}
            executor.run_ncl_script('test.ncl', variables, Path('.'))
            
            # Verify command construction
            expected_cmd = ['ncl', 'var1="value1"', 'var2="value2"', 'test.ncl']
            mock_run.assert_called_once_with(expected_cmd, cwd=Path('.'))
    
    def test_run_fortran_executable(self, mock_logger):
        """Test FORTRAN executable execution"""
        executor = ProcessExecutor(mock_logger)
        
        with patch.object(executor, 'run_command') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            
            executor.run_fortran_executable('test_program', Path('.'))
            
            mock_run.assert_called_once_with(['./test_program'], cwd=Path('.'))


# ============================================================================
# Grid Configuration Tests
# ============================================================================

class TestGridConfigManager:
    """Test the GridConfigManager class"""
    
    def test_detect_cism_5km_grid(self, sample_config, temp_dir, mock_logger, mock_netcdf_file):
        """Test detection of 5km CISM grid"""
        file_manager = FileManager(sample_config, mock_logger)
        grid_manager = GridConfigManager(sample_config, file_manager, mock_logger)
        
        # Create CISM file with 5km dimensions
        sample_config.ism_topo_file = temp_dir / "cism.nc"
        sample_config.working_directory = temp_dir
        mock_netcdf_file(sample_config.ism_topo_file, {'x0': 300, 'y0': 560})
        
        # Create regridding directory
        regrid_dir = temp_dir / "regridding"
        regrid_dir.mkdir()
        
        # Create required data files
        data_files = [
            "CISM1_5km_SCRIP_file.nc",
            "CISM1_5km_weights_file.nc", 
            "CISM1_5km_lat_lon.nc"
        ]
        for filename in data_files:
            (sample_config.data_directory / filename).touch()
        
        grid_manager._detect_cism_grid()
        
        # Verify symlinks were created
        assert (regrid_dir / "source_grid_file.nc").is_symlink()
        assert (regrid_dir / "weights_file.nc").is_symlink()
        assert (regrid_dir / "icesheet_lat_lon.nc").is_symlink()
    
    def test_detect_cism_4km_grid(self, sample_config, temp_dir, mock_logger, mock_netcdf_file):
        """Test detection of 4km CISM grid"""
        file_manager = FileManager(sample_config, mock_logger)
        grid_manager = GridConfigManager(sample_config, file_manager, mock_logger)
        
        # Create CISM file with 4km dimensions
        sample_config.ism_topo_file = temp_dir / "cism.nc"
        sample_config.working_directory = temp_dir
        mock_netcdf_file(sample_config.ism_topo_file, {'x0': 375, 'y0': 700})
        
        # Create regridding directory
        regrid_dir = temp_dir / "regridding"
        regrid_dir.mkdir()
        
        # Create required data files
        data_files = [
            "CISM2_4km_SCRIP_file.nc",
            "CISM2_4km_weights_file.nc", 
            "CISM2_4km_lat_lon.nc"
        ]
        for filename in data_files:
            (sample_config.data_directory / filename).touch()
        
        grid_manager._detect_cism_grid()
        
        # Verify correct files were linked
        assert (regrid_dir / "source_grid_file.nc").resolve().name == "CISM2_4km_SCRIP_file.nc"
    
    def test_detect_cism_incompatible_grid(self, sample_config, temp_dir, mock_logger, mock_netcdf_file):
        """Test error for incompatible CISM grid"""
        file_manager = FileManager(sample_config, mock_logger)
        grid_manager = GridConfigManager(sample_config, file_manager, mock_logger)
        
        # Create CISM file with incompatible dimensions
        sample_config.ism_topo_file = temp_dir / "cism.nc"
        mock_netcdf_file(sample_config.ism_topo_file, {'x0': 999, 'y0': 999})
        
        with pytest.raises(ValidationError, match="incompatible resolution"):
            grid_manager._detect_cism_grid()
    
    def test_detect_cam_fv1_grid(self, sample_config, temp_dir, mock_logger, mock_netcdf_file):
        """Test detection of FV1 CAM grid"""
        file_manager = FileManager(sample_config, mock_logger)
        grid_manager = GridConfigManager(sample_config, file_manager, mock_logger)
        
        # Create CAM file with FV1 dimensions
        sample_config.cam_restart_file = temp_dir / "cam.nc"
        mock_netcdf_file(sample_config.cam_restart_file, {'lon': 288, 'lat': 192})
        
        # Create required data files
        (sample_config.data_directory / "greenland_mask_FV1.nc").touch()
        (sample_config.data_directory / "fv_0.9x1.25_topo_c170415.nc").touch()
        
        grid_manager._detect_cam_grid()
        
        assert sample_config.grid == "fv_0.9x1.25"
        assert sample_config.grid_file == "fv_0.9x1.25.nc"
        assert sample_config.gland_mask_file.name == "greenland_mask_FV1.nc"
    
    def test_detect_cam_fv2_grid(self, sample_config, temp_dir, mock_logger, mock_netcdf_file):
        """Test detection of FV2 CAM grid"""
        file_manager = FileManager(sample_config, mock_logger)
        grid_manager = GridConfigManager(sample_config, file_manager, mock_logger)
        
        # Create CAM file with FV2 dimensions
        sample_config.cam_restart_file = temp_dir / "cam.nc"
        mock_netcdf_file(sample_config.cam_restart_file, {'lon': 144, 'lat': 96})
        
        # Create required data files
        (sample_config.data_directory / "greenland_mask_FV2.nc").touch()
        (sample_config.data_directory / "fv_1.9x2.5_topo_c061116.nc").touch()
        
        grid_manager._detect_cam_grid()
        
        assert sample_config.grid == "fv_1.9x2.5"
        assert sample_config.grid_file == "fv_1.9x2.5.nc"
        assert sample_config.gland_mask_file.name == "greenland_mask_FV2.nc"


# ============================================================================
# Processing Stage Tests
# ============================================================================

class TestRegridStage:
    """Test the RegridStage class"""
    
    def test_regrid_stage_setup(self, sample_config, temp_dir, mock_logger):
        """Test regrid stage setup"""
        file_manager = FileManager(sample_config, mock_logger)
        executor = ProcessExecutor(mock_logger)
        
        # Setup directories and files
        sample_config.working_directory = temp_dir
        regrid_dir = temp_dir / "regridding"
        regrid_dir.mkdir()
        
        # Create required data files
        data_files = [
            "gmted2010_modis-rawdata.nc",
            "template_out.nc",
            "destination_grid_file.nc"
        ]
        for filename in data_files:
            (sample_config.data_directory / filename).touch()
        
        regrid_stage = RegridStage(sample_config, file_manager, executor, mock_logger)
        regrid_stage._setup_regrid_files()
        
        # Verify symlinks were created
        assert (regrid_dir / "highRes-rawdata.nc").is_symlink()
        assert (regrid_dir / "template_out.nc").is_symlink()
        assert (regrid_dir / "destination_grid_file.nc").is_symlink()
    
    def test_regrid_stage_preprocess(self, sample_config, temp_dir, mock_logger, mock_netcdf_file):
        """Test input topography preprocessing"""
        file_manager = FileManager(sample_config, mock_logger)
        executor = Mock(spec=ProcessExecutor)
        
        # Setup
        sample_config.working_directory = temp_dir
        sample_config.ism_topo_file = temp_dir / "input.nc"
        regrid_dir = temp_dir / "regridding"
        regrid_dir.mkdir()
        
        # Create mock input file
        mock_netcdf_file(sample_config.ism_topo_file, {'x0': 300, 'y0': 560})
        
        # Create mock lat/lon file
        lat_lon_file = regrid_dir / "icesheet_lat_lon.nc"
        mock_netcdf_file(lat_lon_file, {'x0': 300, 'y0': 560})
        
        regrid_stage = RegridStage(sample_config, file_manager, executor, mock_logger)
        regrid_stage._preprocess_input_topo()
        
        # Verify NCO commands were called
        assert executor.run_command.call_count == 2
        calls = executor.run_command.call_args_list
        
        # Check ncwa call
        ncwa_cmd = calls[0][0][0]
        assert ncwa_cmd[0] == 'ncwa'
        assert '-v' in ncwa_cmd and 'thk,topg' in ncwa_cmd
        
        # Check ncks call
        ncks_cmd = calls[1][0][0]
        assert ncks_cmd[0] == 'ncks'
        assert '-v' in ncks_cmd and 'lat,lon' in ncks_cmd


class TestBinToCubeStage:
    """Test the BinToCubeStage class"""
    
    def test_generate_namelist(self, sample_config, temp_dir, mock_logger):
        """Test namelist generation"""
        file_manager = FileManager(sample_config, mock_logger)
        executor = Mock(spec=ProcessExecutor)
        
        # Setup
        sample_config.working_directory = temp_dir
        stage_dir = temp_dir / "bin_to_cube"
        stage_dir.mkdir()
        
        # Create regridding output file
        regrid_dir = temp_dir / "regridding"
        regrid_dir.mkdir()
        (regrid_dir / "modified-highRes.nc").touch()
        
        stage = BinToCubeStage(sample_config, file_manager, executor, mock_logger)
        stage._generate_namelist()
        
        # Check namelist file was created
        namelist_file = stage_dir / "bin_to_cube.nl"
        assert namelist_file.exists()
        
        # Check content
        content = namelist_file.read_text()
        assert "raw_latlon_data_file" in content
        assert "ncube=3000" in content
        assert "modified-highRes.nc" in content


class TestCubeToTargetStage:
    """Test the CubeToTargetStage class"""
    
    def test_base_namelist_generation_fv1(self, sample_config, temp_dir, mock_logger):
        """Test base namelist generation for FV1 grid"""
        file_manager = FileManager(sample_config, mock_logger)
        executor = Mock(spec=ProcessExecutor)
        
        # Setup
        sample_config.working_directory = temp_dir
        sample_config.grid = "fv_0.9x1.25"
        sample_config.grid_file = "fv_0.9x1.25.nc"
        
        stage_dir = temp_dir / "cube_to_target"
        stage_dir.mkdir()
        
        # Create required files
        (sample_config.data_directory / "fv_0.9x1.25.nc").touch()
        bin_dir = temp_dir / "bin_to_cube"
        bin_dir.mkdir()
        (bin_dir / "ncube3000.nc").touch()
        
        stage = CubeToTargetStage(sample_config, file_manager, executor, mock_logger)
        stage._generate_base_namelist()
        
        # Check FV1-specific parameters
        assert "ncube_sph_smooth_coarse = 60" in stage.base_namelist
        assert "nwindow_halfwidth = 42" in stage.base_namelist
        assert "nridge_subsample = 8" in stage.base_namelist
    
    def test_base_namelist_generation_fv2(self, sample_config, temp_dir, mock_logger):
        """Test base namelist generation for FV2 grid"""
        file_manager = FileManager(sample_config, mock_logger)
        executor = Mock(spec=ProcessExecutor)
        
        # Setup
        sample_config.working_directory = temp_dir
        sample_config.grid = "fv_1.9x2.5"
        sample_config.grid_file = "fv_1.9x2.5.nc"
        
        stage_dir = temp_dir / "cube_to_target"
        stage_dir.mkdir()
        
        # Create required files
        (sample_config.data_directory / "fv_1.9x2.5.nc").touch()
        bin_dir = temp_dir / "bin_to_cube"
        bin_dir.mkdir()
        (bin_dir / "ncube3000.nc").touch()
        
        stage = CubeToTargetStage(sample_config, file_manager, executor, mock_logger)
        stage._generate_base_namelist()
        
        # Check FV2-specific parameters
        assert "ncube_sph_smooth_coarse = 120" in stage.base_namelist
        assert "nwindow_halfwidth = 84" in stage.base_namelist
        assert "nridge_subsample = 16" in stage.base_namelist
    
    def test_modify_namelist_parameter(self, sample_config, temp_dir, mock_logger):
        """Test namelist parameter modification"""
        file_manager = FileManager(sample_config, mock_logger)
        executor = Mock(spec=ProcessExecutor)
        
        # Setup
        sample_config.working_directory = temp_dir
        sample_config.grid = "fv_0.9x1.25"
        sample_config.grid_file = "fv_0.9x1.25.nc"
        
        stage = CubeToTargetStage(sample_config, file_manager, executor, mock_logger)
        
        # Test parameter modification
        original = "lread_smooth_topofile = .true."
        test_namelist = f"  &topoparams\n    {original}\n  /"
        
        modified = stage._modify_namelist_parameter(test_namelist, 'lread_smooth_topofile', '.false.')
        
        assert "lread_smooth_topofile = .false." in modified
        assert "lread_smooth_topofile = .true." not in modified


class TestPostProcessStage:
    """Test the PostProcessStage class"""
    
    def test_setup_output_dataset(self, sample_config, temp_dir, mock_logger):
        """Test output dataset setup"""
        file_manager = FileManager(sample_config, mock_logger)
        executor = Mock(spec=ProcessExecutor)
        
        # Setup
        sample_config.working_directory = temp_dir
        sample_config.topo_dataset_def = temp_dir / "input_topo.nc"
        sample_config.topo_dataset_def.write_text("test data")
        
        stage_dir = temp_dir / "postproc"
        stage_dir.mkdir()
        
        stage = PostProcessStage(sample_config, file_manager, executor, mock_logger)
        stage._setup_output_dataset()
        
        # Check output file was created
        output_file = sample_config.scratch_run / "topoDataset.nc"
        assert output_file.exists()
        assert output_file.read_text() == "test data"
    
    def test_get_cube_to_target_outputs_fv1(self, sample_config, temp_dir, mock_logger):
        """Test getting cube_to_target output paths for FV1"""
        file_manager = FileManager(sample_config, mock_logger)
        executor = Mock(spec=ProcessExecutor)
        
        # Setup
        sample_config.working_directory = temp_dir
        sample_config.grid = "fv_0.9x1.25"
        
        stage = PostProcessStage(sample_config, file_manager, executor, mock_logger)
        stage._get_cube_to_target_outputs()
        
        # Check expected file paths
        assert "fv_0.9x1.25_nc3000_Nsw042_Nrs008_Co060_Fi001.nc" in str(stage.c2t060)
        assert "fv_0.9x1.25_nc3000_NoAniso_Co008_Fi001.nc" in str(stage.c2t008)
    
    def test_get_cube_to_target_outputs_fv2(self, sample_config, temp_dir, mock_logger):
        """Test getting cube_to_target output paths for FV2"""
        file_manager = FileManager(sample_config, mock_logger)
        executor = Mock(spec=ProcessExecutor)
        
        # Setup
        sample_config.working_directory = temp_dir
        sample_config.grid = "fv_1.9x2.5"
        
        stage = PostProcessStage(sample_config, file_manager, executor, mock_logger)
        stage._get_cube_to_target_outputs()
        
        # Check expected file paths
        assert "fv_1.9x2.5_nc3000_Nsw084_Nrs016_Co120_Fi001.nc" in str(stage.c2t060)
        assert "fv_1.9x2.5_nc3000_NoAniso_Co016_Fi001.nc" in str(stage.c2t008)


# ============================================================================
# Integration Tests
# ============================================================================

class TestTopographyProcessorIntegration:
    """Integration tests for the full TopographyProcessor"""
    
    def test_processor_initialization(self, sample_config):
        """Test processor initialization"""
        processor = TopographyProcessor(sample_config)
        
        assert processor.config == sample_config
        assert processor.logger is not None
        assert processor.env_manager is not None
        assert processor.file_manager is not None
        assert processor.executor is not None
        assert processor.grid_manager is not None
        
        # Check all stages are initialized
        assert processor.regrid_stage is not None
        assert processor.bin_to_cube_stage is not None
        assert processor.cube_to_target_stage is not None
        assert processor.postproc_stage is not None
    
    def test_setup_and_validate_success(self, sample_config, temp_dir, mock_netcdf_file):
        """Test successful setup and validation"""
        processor = TopographyProcessor(sample_config)
        
        # Create required files and directories
        sample_config.ism_topo_file = temp_dir / "cism.nc"
        sample_config.cam_restart_file = temp_dir / "cam.nc"
        sample_config.working_directory = temp_dir / "work"
        
        # Create NetCDF files with proper dimensions
        mock_netcdf_file(sample_config.ism_topo_file, {'x0': 300, 'y0': 560})
        mock_netcdf_file(sample_config.cam_restart_file, {'lon': 288, 'lat': 192})
        
        # Create directories
        sample_config.working_directory.mkdir(parents=True)
        
        # Create required data files
        data_files = [
            "CISM1_5km_SCRIP_file.nc",
            "CISM1_5km_weights_file.nc",
            "CISM1_5km_lat_lon.nc",
            "greenland_mask_FV1.nc",
            "fv_0.9x1.25_topo_c170415.nc"
        ]
        for filename in data_files:
            (sample_config.data_directory / filename).touch()
        
        # Mock environment setup
        with patch.object(processor.env_manager, 'setup_environment'):
            processor._setup_and_validate()
        
        # Check configuration was set up correctly
        assert sample_config.grid == "fv_0.9x1.25"
        assert sample_config.grid_file == "fv_0.9x1.25.nc"
    
    def test_setup_validation_failure(self, sample_config, temp_dir):
        """Test validation failure"""
        processor = TopographyProcessor(sample_config)
        
        # Don't create required files - should fail validation
        sample_config.ism_topo_file = temp_dir / "nonexistent.nc"
        
        with patch.object(processor.env_manager, 'setup_environment'):
            with pytest.raises(ValidationError):
                processor._setup_and_validate()


# ============================================================================
# Comparison and Validation Tests
# ============================================================================

class TestNetCDFComparison:
    """Test NetCDF file comparison utilities"""
    
    def test_identical_files(self, temp_dir, mock_netcdf_file):
        """Test comparison of identical files"""
        file1 = temp_dir / "file1.nc"
        file2 = temp_dir / "file2.nc"
        
        # Create identical files
        data = np.array([[1.0, 2.0], [3.0, 4.0]])
        file_spec = {
            'test_var': {
                'dtype': 'f8',
                'dimensions': ('x', 'y'),
                'data': data,
                'attributes': {'units': 'meters'}
            }
        }
        
        mock_netcdf_file(file1, {'x': 2, 'y': 2}, file_spec)
        mock_netcdf_file(file2, {'x': 2, 'y': 2}, file_spec)
        
        result = compare_netcdf_files(file1, file2)
        
        assert result['files_identical'] is True
        assert result['max_absolute_difference'] == 0.0
        assert len(result['data_differences']) == 0
    
    def test_different_dimensions(self, temp_dir, mock_netcdf_file):
        """Test comparison of files with different dimensions"""
        file1 = temp_dir / "file1.nc"
        file2 = temp_dir / "file2.nc"
        
        mock_netcdf_file(file1, {'x': 2, 'y': 2})
        mock_netcdf_file(file2, {'x': 3, 'y': 2})
        
        result = compare_netcdf_files(file1, file2)
        
        assert result['files_identical'] is False
        assert result['dimension_differences']['size_differences']['x'] == (2, 3)
    
    def test_different_variables(self, temp_dir, mock_netcdf_file):
        """Test comparison of files with different variables"""
        file1 = temp_dir / "file1.nc"
        file2 = temp_dir / "file2.nc"
        
        dims = {'x': 2, 'y': 2}
        data = np.array([[1.0, 2.0], [3.0, 4.0]])
        
        vars1 = {
            'var1': {
                'dtype': 'f8',
                'dimensions': ('x', 'y'),
                'data': data
            }
        }
        
        vars2 = {
            'var2': {
                'dtype': 'f8',
                'dimensions': ('x', 'y'),
                'data': data
            }
        }
        
        mock_netcdf_file(file1, dims, vars1)
        mock_netcdf_file(file2, dims, vars2)
        
        result = compare_netcdf_files(file1, file2)
        
        assert result['files_identical'] is False
        assert 'var1' in result['variable_differences']['file1_only']
        assert 'var2' in result['variable_differences']['file2_only']
    
    def test_numerical_differences(self, temp_dir, mock_netcdf_file):
        """Test comparison of files with numerical differences"""
        file1 = temp_dir / "file1.nc"
        file2 = temp_dir / "file2.nc"
        
        dims = {'x': 2, 'y': 2}
        data1 = np.array([[1.0, 2.0], [3.0, 4.0]])
        data2 = np.array([[1.0, 2.0], [3.0, 4.001]])  # Small difference
        
        vars1 = {
            'test_var': {
                'dtype': 'f8',
                'dimensions': ('x', 'y'),
                'data': data1
            }
        }
        
        vars2 = {
            'test_var': {
                'dtype': 'f8',
                'dimensions': ('x', 'y'),
                'data': data2
            }
        }
        
        mock_netcdf_file(file1, dims, vars1)
        mock_netcdf_file(file2, dims, vars2)
        
        result = compare_netcdf_files(file1, file2, tolerance=1e-6)
        
        assert result['files_identical'] is False
        assert result['max_absolute_difference'] == 0.001
        assert len(result['data_differences']) == 1
        assert result['data_differences'][0]['variable'] == 'test_var'
    
    def test_within_tolerance(self, temp_dir, mock_netcdf_file):
        """Test comparison within tolerance"""
        file1 = temp_dir / "file1.nc"
        file2 = temp_dir / "file2.nc"
        
        dims = {'x': 2, 'y': 2}
        data1 = np.array([[1.0, 2.0], [3.0, 4.0]])
        data2 = np.array([[1.0, 2.0], [3.0, 4.0000000001]])  # Very small difference
        
        vars1 = {
            'test_var': {
                'dtype': 'f8',
                'dimensions': ('x', 'y'),
                'data': data1
            }
        }
        
        vars2 = {
            'test_var': {
                'dtype': 'f8',
                'dimensions': ('x', 'y'),
                'data': data2
            }
        }
        
        mock_netcdf_file(file1, dims, vars1)
        mock_netcdf_file(file2, dims, vars2)
        
        result = compare_netcdf_files(file1, file2, tolerance=1e-6)
        
        assert result['files_identical'] is True  # Within tolerance
        assert result['max_absolute_difference'] < 1e-6


# ============================================================================
# Performance and Benchmarking Tests
# ============================================================================

class TestPerformance:
    """Test performance-related functionality"""
    
    def test_file_operations_performance(self, sample_config, temp_dir, mock_logger):
        """Test file operations don't take excessive time"""
        import time
        
        file_manager = FileManager(sample_config, mock_logger)
        
        # Create many files
        num_files = 100
        for i in range(num_files):
            (sample_config.scratch_run / f"test_{i:03d}.nc").touch()
        
        # Time the latest file search
        start_time = time.time()
        latest = file_manager.find_latest_restart_file("test_*.nc")
        elapsed = time.time() - start_time
        
        # Should complete quickly (< 1 second even for many files)
        assert elapsed < 1.0
        assert latest.name == "test_099.nc"
    
    def test_netcdf_comparison_performance(self, temp_dir, mock_netcdf_file):
        """Test NetCDF comparison performance"""
        import time
        
        file1 = temp_dir / "large1.nc"
        file2 = temp_dir / "large2.nc"
        
        # Create larger test files
        dims = {'x': 100, 'y': 100}
        data = np.random.random((100, 100))
        
        vars_spec = {
            'test_var': {
                'dtype': 'f8',
                'dimensions': ('x', 'y'),
                'data': data
            }
        }
        
        mock_netcdf_file(file1, dims, vars_spec)
        mock_netcdf_file(file2, dims, vars_spec)
        
        # Time the comparison
        start_time = time.time()
        result = compare_netcdf_files(file1, file2)
        elapsed = time.time() - start_time
        
        # Should complete in reasonable time
        assert elapsed < 5.0  # 5 seconds for 100x100 array
        assert result['files_identical'] is True


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_validation_error_inheritance(self):
        """Test custom exception inheritance"""
        error = ValidationError("Test error")
        assert isinstance(error, ValidationError)
        assert isinstance(error, TopoProcessingError)
        assert isinstance(error, Exception)
    
    def test_processing_stage_error_inheritance(self):
        """Test processing stage error inheritance"""
        error = ProcessingStageError("Stage failed")
        assert isinstance(error, ProcessingStageError)
        assert isinstance(error, TopoProcessingError)
        assert isinstance(error, Exception)
    
    def test_environment_error_inheritance(self):
        """Test environment error inheritance"""
        error = EnvironmentError("Environment setup failed")
        assert isinstance(error, EnvironmentError)
        assert isinstance(error, TopoProcessingError)
        assert isinstance(error, Exception)
    
    def test_file_manager_error_scenarios(self, sample_config, temp_dir, mock_logger):
        """Test various file manager error scenarios"""
        file_manager = FileManager(sample_config, mock_logger)
        
        # Test empty file
        empty_file = temp_dir / "empty.nc"
        empty_file.touch()
        sample_config.ism_topo_file = empty_file
        sample_config.cam_restart_file = temp_dir / "cam.nc"
        sample_config.cam_restart_file.touch()
        sample_config.working_directory = temp_dir
        
        with pytest.raises(ValidationError, match="File is empty"):
            file_manager._validate_file_existence()
    
    def test_process_executor_error_scenarios(self, mock_logger):
        """Test process executor error scenarios"""
        executor = ProcessExecutor(mock_logger)
        
        # Test non-existent command
        with pytest.raises(ProcessingStageError):
            executor.run_command(['nonexistent_command'])
        
        # Test command with bad arguments
        with pytest.raises(ProcessingStageError):
            executor.run_command(['ls', '--invalid-option'])


# ============================================================================
# Test Configuration and Runners
# ============================================================================

class TestConfiguration:
    """Test configuration and setup"""
    
    def test_pytest_configuration(self):
        """Test that pytest is configured correctly"""
        assert pytest.__version__ is not None
        
    def test_required_imports(self):
        """Test that all required modules can be imported"""
        import netCDF4
        import numpy
        import tempfile
        import pathlib
        
        assert netCDF4.__version__ is not None
        assert numpy.__version__ is not None


# ============================================================================
# Integration Test with Mock Bash Script
# ============================================================================

class TestBashComparison:
    """Test comparison with mock bash script results"""
    
    def test_mock_bash_comparison(self, temp_dir, mock_netcdf_file):
        """Test comparison against mock bash script results"""
        
        # Create mock "bash output" file
        bash_output = temp_dir / "bash_topoDataset.nc"
        python_output = temp_dir / "python_topoDataset.nc"
        
        # Create identical data
        dims = {'lon': 288, 'lat': 192}
        phis_data = np.random.random((192, 288))
        sgh_data = np.random.random((192, 288))
        
        vars_spec = {
            'PHIS': {
                'dtype': 'f8',
                'dimensions': ('lat', 'lon'),
                'data': phis_data,
                'attributes': {'units': 'm2/s2', 'long_name': 'surface geopotential'}
            },
            'SGH': {
                'dtype': 'f8',
                'dimensions': ('lat', 'lon'),
                'data': sgh_data,
                'attributes': {'units': 'm', 'long_name': 'standard deviation of orography'}
            }
        }
        
        # Create both files with same data
        mock_netcdf_file(bash_output, dims, vars_spec)
        mock_netcdf_file(python_output, dims, vars_spec)
        
        # Compare
        result = compare_netcdf_files(bash_output, python_output)
        
        assert result['files_identical'] is True
        assert result['max_absolute_difference'] == 0.0
        
    def test_acceptable_differences(self, temp_dir, mock_netcdf_file):
        """Test that small differences are within acceptable tolerances"""
        
        bash_output = temp_dir / "bash_topoDataset.nc"
        python_output = temp_dir / "python_topoDataset.nc"
        
        dims = {'lon': 288, 'lat': 192}
        
        # Create nearly identical data with tiny differences
        base_data = np.random.random((192, 288))
        bash_data = base_data
        python_data = base_data + np.random.normal(0, 1e-13, (192, 288))  # Very small noise
        
        vars_spec_bash = {
            'PHIS': {
                'dtype': 'f8',
                'dimensions': ('lat', 'lon'),
                'data': bash_data
            }
        }
        
        vars_spec_python = {
            'PHIS': {
                'dtype': 'f8',
                'dimensions': ('lat', 'lon'),
                'data': python_data
            }
        }
        
        mock_netcdf_file(bash_output, dims, vars_spec_bash)
        mock_netcdf_file(python_output, dims, vars_spec_python)
        
        # Compare with appropriate tolerance
        result = compare_netcdf_files(bash_output, python_output, tolerance=1e-12)
        
        # Should be identical within tolerance
        assert result['files_identical'] is True or result['max_absolute_difference'] < 1e-12


# ============================================================================
# Main Test Runner
# ============================================================================

if __name__ == "__main__":
    """Run the test suite"""
    
    # Configure pytest arguments
    pytest_args = [
        __file__,
        "-v",  # Verbose output
        "--tb=short",  # Short traceback format
        "--durations=10"  # Show 10 slowest tests
   ]
    
    # Run with coverage if available
    try:
        import pytest_cov
        pytest_args.extend(["--cov-fail-under=80"])  # Require 80% coverage
    except ImportError:
        print("pytest-cov not available, running without coverage")
    
    # Run the tests
    exit_code = pytest.main(pytest_args)
    
    if exit_code == 0:
        print("\n✅ All tests passed!")
    else:
        print(f"\n❌ Tests failed with exit code {exit_code}")
    
    sys.exit(exit_code)
