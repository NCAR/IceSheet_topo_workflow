#!/bin/bash
#
#BSUB -P P06010014
#BSUB -W 01:00
#BSUB -n 1
#BSUB -o CAM_topo_regen.stdout.%J
#BSUB -e CAM_topo_regen.stderr.%J
#BSUB -q caldera
#BSUB -J CAM_topo_regen
#
# -------------------------------------------------------------------------
# J. Fyke: call topography-updating routine for CAM
#
#This script is intended to be called during restarts of CESM, to update 
#FV1-degree CAM topography in response to 5-km resolution Greenland CISM geometry 
#changes prior to the next runstep.
#
#It can also be used offline to generate CAM grids corresponding to any arbitrary 
#ice sheet grid.
#
#This script uses several FORTRAN programs that MUST BE COMPILED AHEAD OF TIME.
#
#This script requires a large memory footprint, and operates on large (GB) files.
#
#This script reads in the bed topography and thickness from a 5 or 4-km resolution 
#Greenland CISM restart file, converts this to a surface topography, then merges
#this topography into a high-res global topography.  This is then used as input 
#to CAM topography and subgrid-roughness-generating routines, to derive new 
#FV1-degree PHIS and SGH* fields, which are finally inserted into a CAM restart 
#file, overwriting the existing PHIS and SGH* fields.
#
#Required inputs:
#1) ISM_Topo_File: source of ice sheet topography.  This will be set by scripts
#during run-time.
#2) CAM_Restart_File: the destination of the updated PHIS and SGH* fields.
#3) Working_Directory: location where this script is being run, and where the sub-
#directories containing the necessary tools preside (these directories include:
#     -regridding 
#     -phis_smoothing (deleted 2017-04-14)
#     -bin_to_cube
#     -cube_to_target)
#4) Data_Directory: the location of the directory containing a number of input
#datasets that are necessary for the above tools.  Where possible, soft-links
#are generated below, to these tools.  However, in some cases, files are copied
#into Working_Directory.
#
# -------------------------------------------------------------------------
# Update
# M. Lofverstrom
# - added support for different resolutions and new GrIS file
# - updated routines: bin_to_cube & cube_to_target (https://github.com/NCAR/Topo/ and special version of cube_to_taget)
#   topography smoothing on cubed sphere grid
# - faster routines with special treatment of Greenland
# - postprocessing routine
# -------------------------------------------------------------------------

module load nco/4.4.2
module load ncl/6.3.0
module load python/2.7.7

#####

ScratchRun=$PWD/../

#####

echo "****Running CAM topography-updating routine...****"

echo "-> Setting location of necessary input/output files and directories"

Test_topo_regen=false

## Select high resolution topography data set ("gmted2010" (def) or "usgs")
highResDataset=gmted2010 
#highResDataset=usgs

if [ "$Test_topo_regen" == false ]; then 

  echo "Defining I/O files for coupled run topography regeneration."
  ####Points to most recently modified CISM restart file in $RunDir 
  export ISM_Topo_File=`ls -t $ScratchRun/*.cism.r.* | head -n 1`
  ####Points to most recently modified CAM restart file in $RunDir
  export CAM_Restart_File=`ls -t $ScratchRun/*.cam.r.* | head -n 1`
  export Temporary_output_file=$ScratchRun/Temporary_output_file.nc
  ####Points to dyn_topog working directory, that is within run directory
  export Working_Directory=$ScratchRun/dynamic_atm_topog            

elif [ "$Test_topo_regen" == true ]; then  

  echo "WARNING: USING PATHS TO TOPOGRAPHY REGENERATION TEST FILES!"
  
  ###THESE ARE TEMPORARY 4 km ISM grid TEST PATHS
  export ISM_Topo_File=$ScratchRun/temp_io_files/4km_ISM/BG_MG1_CISM2.cism.r.0010-01-01-00000.nc
  export CAM_Restart_File=$ScratchRun/temp_io_files/4km_ISM/BG_MG1_CISM2.cam.r.0010-01-01-00000.nc
  export Temporary_output_file=$ScratchRun/Temporary_output_file.nc
  export Working_Directory=$ScratchRun
  ####

else

  echo "Error: = Test_topo_regen not defined as 'true' or 'false'"
  exit

fi

export Data_Directory=/glade/p/cesm/liwg/cam_dyn_topog_data

echo "Input CISM restart file is $ISM_Topo_File"
echo "CAM restart file (only used for an array size check) is $CAM_Restart_File"

if [ ! -e $ISM_Topo_File ]; then
  echo "   Error: Ice sheet topography input file $ISM_Topo_File does not exist"
  exit
fi
if [ ! -e $CAM_Restart_File ]; then
  echo "   Error: CAM restart file $CAM_Restart_File does not exist"
  exit
fi 
echo "   Success: input/output files exist:"
echo "   Ice sheet topography input file = $ISM_Topo_File"
echo "   CAM restart file = $CAM_Restart_File"

#Check that incoming CAM and CISM restart files are the right size

if ncdump -h $ISM_Topo_File | grep -q 'x0 = 300' && ncdump -h $ISM_Topo_File | grep -q 'y0 = 560'; then
 echo "   Based on dimension size, CISM topography input APPEARS to be on a 5km CISM grid"
 # Source SCRIP file
 ln -sfv $Data_Directory/CISM1_5km_SCRIP_file.nc   $Working_Directory/regridding/source_grid_file.nc   
 # Weight file between IS and USGS tile grids
 ln -sfv $Data_Directory/CISM1_5km_weights_file.nc $Working_Directory/regridding/weights_file.nc       
 # Ice sheet lat/lon fields
 ln -sfv $Data_Directory/CISM1_5km_lat_lon.nc      $Working_Directory/regridding/icesheet_lat_lon.nc   

elif ncdump -h $ISM_Topo_File | grep -q 'x0 = 375' && ncdump -h $ISM_Topo_File | grep -q 'y0 = 700'; then
 echo "   Based on dimension size, CISM topography input APPEARS to be on a 4km CISM grid"
 # Source SCRIP file
 ln -sfv $Data_Directory/CISM2_4km_SCRIP_file.nc   $Working_Directory/regridding/source_grid_file.nc   
 # Weight file between IS and USGS tile grids
 ln -sfv $Data_Directory/CISM2_4km_weights_file.nc $Working_Directory/regridding/weights_file.nc       
 # Ice sheet lat/lon fields 
 ln -sfv $Data_Directory/CISM2_4km_lat_lon.nc      $Working_Directory/regridding/icesheet_lat_lon.nc   


elif ncdump -h $ISM_Topo_File | grep -q 'x1 = 393' && ncdump -h $ISM_Topo_File | grep -q 'y1 = 695'; then
 ## Note that this dataset only has dims x1 and y1; dims x0 and y0 are missing...
 echo "   Based on dimension size, CISM topography input APPEARS to be on a 4km CISM grid (version from 2016-12-19)"
 # Source SCRIP file
 ln -sfv $Data_Directory/CISM2_4km_2016_12_19_SCRIP_file.nc   $Working_Directory/regridding/source_grid_file.nc   
 # Weight file between IS and USGS tile grids
 ln -sfv $Data_Directory/CISM2_4km_2016_12_19_weights_file.nc $Working_Directory/regridding/weights_file.nc       
 # Ice sheet lat/lon fields 
 ln -sfv $Data_Directory/CISM2_4km_2016_12_19_lat_lon.nc      $Working_Directory/regridding/icesheet_lat_lon.nc   


elif ncdump -h $ISM_Topo_File | grep -q 'x1 = 416' && ncdump -h $ISM_Topo_File | grep -q 'y1 = 704'; then
 ## Note that this dataset only has dims x1 and y1; dims x0 and y0 are missing...
 echo "   Based on dimension size, CISM topography input APPEARS to be on a 4km CISM grid (version from 2017-04-29)"
 # Source SCRIP file
 ln -sfv $Data_Directory/CISM2_4km_2017_04_29_SCRIP_file.nc   $Working_Directory/regridding/source_grid_file.nc
 # Weight file between IS and USGS tile grids
 ln -sfv $Data_Directory/CISM2_4km_2017_04_29_weights_file.nc $Working_Directory/regridding/weights_file.nc
 # Ice sheet lat/lon fields
 ln -sfv $Data_Directory/CISM2_4km_2017_04_29_lat_lon.nc      $Working_Directory/regridding/icesheet_lat_lon.nc


else
 echo "  Error: CISM topography input appears to be of an incompatible resolution with current script"  
 exit
fi



if ncdump -h $CAM_Restart_File | grep -q 'lon = 288' && ncdump -h $CAM_Restart_File | grep -q 'lat = 192'; then
 echo "   Based on dimension size, CAM data APPEARS to be on a FV1 CESM grid"
 cami=cami_fv1.nc
 targetFile=targetFV1.nc
 grid=fv_0.9x1.25
 gridFile=$grid.nc
 glandMaskFile=$Data_Directory/greenland_mask_FV1.nc
 topoDatasetDef=$Data_Directory/fv_0.9x1.25_topo_c170415.nc


elif ncdump -h $CAM_Restart_File | grep -q 'lon = 144' && ncdump -h $CAM_Restart_File | grep -q 'lat = 96'; then
 echo "   Based on dimension size, CAM data APPEARS to be on a FV2 CESM grid"
 cami=cami_fv2.nc
 targetFile=targetFV2.nc
 grid=fv_1.9x2.5
 gridFile=$grid.nc
 glandMaskFile=$Data_Directory/greenland_mask_FV2.nc
 topoDatasetDef=$Data_Directory/fv_1.9x2.5_topo_c061116.nc

else
  echo "  Error: CAM restart appears to be of an incompatible resolution with current script"  
  exit
fi

echo "   Success: Restart files are correct resolutions"

if [ ! -d $Working_Directory ]; then
  echo "   Error: $Working_Directory is not a valid working directory"
  exit
fi
if [ ! -d $Data_Directory ]; then
  echo "   Error: $Data_Directory is not a valid input data directory"
  exit
fi
echo "   Success: Working and data directories exist"

cd $Working_Directory

#########################

echo " "
echo "-> Regridding model topography onto a lat-lon tile, insert into global dataset"

cd $Working_Directory/regridding


if [ "$highResDataset" == gmted2010 ]; then
    ln -sfv $Data_Directory/gmted2010_modis-rawdata.nc  $Working_Directory/regridding/highRes-rawdata.nc
elif [ "$highResDataset" == usgs ]; then 
    ln -sfv $Data_Directory/usgs-rawdata.nc  $Working_Directory/regridding/highRes-rawdata.nc
fi


# Ice-sheet-grid diagnostic
ln -sfv $Data_Directory/template_out.nc          $Working_Directory/regridding/template_out.nc
ln -sfv $Data_Directory/destination_grid_file.nc $Working_Directory/regridding/destination_grid_file.nc


echo "   Creating regridded topography file and merging this into topography"

# Pre-process input topography file.
ncwa -O -a time -v thk,topg $ISM_Topo_File input_topography_file.nc
ncks -A -v lat,lon icesheet_lat_lon.nc input_topography_file.nc

# Remove existing archived regridded file and modified global topography files if they exist
if [ -e ISM30sec.archived.nc ]; then
  rm ISM30sec.archived.nc 
fi
if [ -e modified_usgs.nc ]; then
  rm modified-highRes.nc
fi
if [ -e regridded-tile.nc ]; then
  rm regridded-tile.nc
fi

# Copy original global topography dataset into local version, into which CISM topography will be merged
cp -f highRes-rawdata.nc modified-highRes.nc 

# Regrid ice sheet onto 30-sec lat/lon tiled grid
ncl 'input_file_name="input_topography_file.nc"' 'global_file_name="modified-highRes.nc"' 'output_file_name="regridded-tile.nc"' regrid.ncl

# Merge tile with global high resolution dataset
python mergeTile.py 'modified-highRes.nc' 'regridded-tile.nc'

################

echo " "
echo "-> Running bin_to_cube generator..."
      
cd $Working_Directory/bin_to_cube

ln -sfv $Data_Directory/landm_coslat.nc landm_coslat.nc

cat > bin_to_cube.nl <<EOF
&binparams
  raw_latlon_data_file = '$Working_Directory/regridding/modified-highRes.nc'
  output_file = 'ncube3000.nc'
  ncube=3000
/
EOF

echo "   Running bin_to_cube..."
./bin_to_cube


################

echo "-> Running cube_to_target SGH/SGH30 generator..."
       
cd $Working_Directory/cube_to_target

cat > cube_to_target.nl <<EOF
&topoparams
  grid_descriptor_fname           = '$Data_Directory/$gridFile'
  output_grid                     = '$grid'
  intermediate_cubed_sphere_fname = '$Working_Directory/bin_to_cube/ncube3000.nc'
  output_fname                    = 'junk'
  externally_smoothed_topo_file   = 'junk'
  lsmooth_terr = .false.
  lexternal_smooth_terr = .false.
  lzero_out_ocean_point_phis = .false.
  lzero_negative_peaks = .true.
  lsmooth_on_cubed_sphere = .true.
  ncube_sph_smooth_coarse = 60
  ncube_sph_smooth_fine = 1
  ncube_sph_smooth_iter = 1
  lfind_ridges = .true.
  lridgetiles = .false.
  nwindow_halfwidth = 42
  nridge_subsample = 8
  lread_smooth_topofile = .true.
/
EOF

echo "   Running cube_to_target..."


#PHASE 1a
# --- smooth topo w/ 60-point smoother
sed '/lread_smooth_topofile/s/.true./.false./' < cube_to_target.nl > tmp.nl
cp tmp.nl cube_to_target.nl
./cube_to_target

#PHASE 1b
# --- find ridges on 60-point deviations
# --- and map to FV model grid
sed '/lread_smooth_topofile/s/.false./.true./' < cube_to_target.nl > tmp2.nl
cp tmp2.nl cube_to_target.nl
sed '/lfind_ridges/s/.true./.false./' < cube_to_target.nl > tmp2.nl ## may need this
cp tmp2.nl cube_to_target.nl
./cube_to_target

#PHASE 2a
# --- smooth topo w/ 8-point smoother for
# --- Greenland SGH30 adjustment
sed '/lread_smooth_topofile/s/.true./.false./' < cube_to_target.nl > tmp3.nl
cp tmp3.nl cube_to_target.nl
sed '/ncube_sph_smooth_coarse/s/60/8/' < cube_to_target.nl > tmp3.nl
cp tmp3.nl cube_to_target.nl
./cube_to_target

#PHASE 2b
# --- skip ridges but map to FV model grid
sed '/lread_smooth_topofile/s/.false./.true./' < cube_to_target.nl > tmp4.nl
cp tmp4.nl cube_to_target.nl
sed '/lfind_ridges/s/.true./.false./' < cube_to_target.nl > tmp4.nl
cp tmp4.nl cube_to_target.nl
./cube_to_target


################

echo "-> Merging datasets..."

cd $Working_Directory/postproc

topoDataset=$ScratchRun/topoDataset.nc
cp $topoDatasetDef $topoDataset

c2tOutputDir=$Working_Directory/cube_to_target/output
c2t060=$c2tOutputDir/${grid}_nc3000_Nsw042_Nrs008_Co060_Fi001.nc
c2t008=$c2tOutputDir/${grid}_nc3000_NoAniso_Co008_Fi001.nc

python postproc_mask.py $CAM_Restart_File $topoDataset $glandMaskFile $c2t060 $c2t008

################

echo ""
echo "-> Topography updating finished successfully"
echo "-> Returning to working directory"
cd $Working_Directory

exit

## == end of script == ##
