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
# Tailored for CISL Cheyenne
#
###########################

module load nco

if [ $SHELL == /bin/bash ]; then
    source /glade/u/apps/ch/opt/Lmod/7.3.14/lmod/7.3.14/init/bash
elif [ $SHELL == /bin/tcsh ]; then
    source /glade/u/apps/ch/opt/Lmod/7.3.14/lmod/7.3.14/init/tcsh
fi

## Default settings (may be changed from setup.sh)
Project=P93300301
Walltime=00:45:00
Queue=regular

ScratchRun=/glade/scratch/cmip6/b.e21.B1850G.f09_g17_gl4.CMIP6-ssp585-withism.001/run
ScriptDir=$ScratchRun/dynamic_atm_topog/

### ### ### ### ### ### ### ###

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

## Submit topography regeneration script to Cheyenne queue
if [ -f $CISM_Restart_File ]; then
    echo "Submitting topography regeneration script"
    qsub -l select=1:ncpus=1 -l walltime=$Walltime -q $Queue -A $Project $ScriptDir/CAM_topo_regen.sh

fi

## === end of script === ##
