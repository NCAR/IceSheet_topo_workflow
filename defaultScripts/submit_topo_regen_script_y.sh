#!/bin/bash
#
# This script has two main purposes:
# (1) Submit topography regeneration as a separate 
#     process running in parallel with CESM submission
#
# (2) Merge updated topography with CAM restart 
#     file if possible
#
# Author:
# M. Lofverstrom
# NCAR, April 2017
#
###########################
#
# Tailored for CISM Yellowstone
#
###########################


module load nco/4.4.2

ScratchRun=$PWD/../
ScriptDir=$PWD/

CAM_Restart_File=`ls -t $ScratchRun/*.cam.r.* | head -n 1`
CISM_Restart_File=`ls -t $ScratchRun/*.cism.r.* | head -n 1`
#Temporary_output_file=$ScratchRun/Temporary_output_file.nc

## Update CAM restart file
#if [ -f $Temporary_output_file ]; then
#   echo "Temporary file exists!"
#   echo "Updating CAM restart file"
#   ncks -A -v SGH,SGH30,PHIS $Temporary_output_file $CAM_Restart_File
#else
#   echo "Temporary topography file not found!"
#   echo "Will not try to update the CAM restart file"
#fi

## Submit topography regeneration script to queue
if [ -f $CISM_Restart_File ]; then
    echo "Submitting topography regeneration script"
    bsub < $ScriptDir/CAM_topo_regen.sh
fi

## === end of script === ##
