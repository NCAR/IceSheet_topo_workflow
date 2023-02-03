#!/bin/bash

###########################
#
# Configure topography updating 
# routines for Yellowstone and 
# Cheyenne architecture
#
# Author:
# M. Lofverstrom
# NCAR, 2017
#
###########################

while [[ $# -gt 1 ]]
do
key="$1"

case $key in
    -r|--rundir)
    ScratchRun="$2"
    shift 
    ;;
    -p|--project)
    Project="$2"
    shift 
    ;;
    -w|--walltime)
    Walltime="$2"
    shift 
    ;;
    -q|--queue)
    Queue="$2"
    shift
    ;;
    *)
    ;;
esac
shift
done


ScriptDir=$ScratchRun/dynamic_atm_topog
ScriptDefault=${ScriptDir}/defaultScripts


#######


if [[ $(hostname) = yslogin* ]]; then
    machine=yellowstone
elif [[ $(hostname) = geyser* ]]; then
    machine=yellowstone
elif [[ $(hostname) = cheyenne* ]]; then
    machine=cheyenne
fi


### ### ### ### ### ### ### ### 


if [[ $machine == yellowstone ]]; then

    cp ${ScriptDefault}/CAM_topo_regen_y.sh ${ScriptDir}/CAM_topo_regen.sh
    cp ${ScriptDefault}/submit_topo_regen_script_y.sh \
	${ScriptDir}/submit_topo_regen_script.sh

    regenS=${ScriptDir}/CAM_topo_regen.sh
    submitS=${ScriptDir}/submit_topo_regen_script.sh

    ###

#    nco=nco/4.4.2
#    ncl=ncl/6.3.0
#    python=python/2.7.7

#    sed -i "/module load nco/c\module load $nco" $submitS
#    sed -i "/module load nco/c\module load $nco" $regenS
#    sed -i "/module load ncl/c\module load $ncl" $regenS
#    sed -i "/module load python/c\module load $python" $regenS

    ###

    if [[ -n ${ScratchRun} ]]; then 
	sed -i "/ScratchRun=/c\ScratchRun=${ScratchRun}" $submitS
    fi

    if [[ -n ${ScriptDir} ]]; then 
	sed -i "/ScriptDir=/c\ScriptDir=${ScriptDir}" $submitS
    fi

    ##

    if [[ -n ${ScratchRun} ]]; then 
	sed -i "/ScratchRun=/c\ScratchRun=${ScratchRun}" $regenS
    fi
    if [[ -n ${Project} ]]; then 
	sed -i "/#BSUB -P/c\#BSUB -P ${Project}" $regenS
    fi
    if [[ -n ${Walltime} ]]; then 
	sed -i "/#BSUB -W/c\#BSUB -W ${Walltime}" $regenS
    fi
    if [[ -n ${Queue} ]]; then 
	sed -i "/#BSUB -q/c\#BSUB -q ${Queue}" $regenS
    fi

fi


### ### ### ### ### ### ### ### 


if [[ $machine == cheyenne ]]; then

    cp ${ScriptDefault}/CAM_topo_regen_c.sh ${ScriptDir}/CAM_topo_regen.sh
    cp ${ScriptDefault}/submit_topo_regen_script_c.sh \
	${ScriptDir}/submit_topo_regen_script.sh

    regenS=${ScriptDir}/CAM_topo_regen.sh
    submitS=${ScriptDir}/submit_topo_regen_script.sh

    ###

#    nco=nco/4.6.2
#    ncl=ncl/6.4.0
#    python=python/2.7.13

    ## Probably not necessay
    if [ $SHELL == /bin/bash ]; then
	source /glade/u/apps/ch/opt/Lmod/7.3.14/lmod/7.3.14/init/bash
    elif [ $SHELL == /bin/tcsh ]; then
	source /glade/u/apps/ch/opt/Lmod/7.3.14/lmod/7.3.14/init/tcsh
    fi


#    sed -i "/module load nco/c\module load $nco" $submitS
#    sed -i "/module load nco/c\module load $nco" $regenS
#    sed -i "/module load ncl/c\module load $ncl" $regenS
#    sed -i "/module load python/c\module load $python" $regenS

    ###

    if [[ -n ${ScratchRun} ]]; then 
	sed -i "/ScratchRun=/c\ScratchRun=${ScratchRun}" $submitS
    fi
    if [[ -n ${ScriptDir} ]]; then 
	sed -i "/SciptDir=/c\ScriptDir=${ScriptDir}" $submitS
    fi

    if [[ -n ${Project} ]]; then 
	sed -i "/Project=/c\Project=${Project}" $submitS
    fi
    if [[ -n ${Walltime} ]]; then 
	sed -i "/Walltime=/c\Walltime=${Walltime}" $submitS
    fi
    if [[ -n ${Queue} ]]; then 
	sed -i "/Queue=/c\Queue=${Queue}" $submitS
    fi


    ##

    if [[ -n ${ScratchRun} ]]; then 
	sed -i "/ScratchRun=/c\ScratchRun=${ScratchRun}" $regenS
    fi
    if [[ -n ${Project} ]]; then 
	sed -i "/#PBS -A/c\#PBS -A ${Project}" $regenS
    fi
    if [[ -n ${Walltime} ]]; then 
	sed -i "/#PBS -l w/c\#PBS -l walltime=${Walltime}" $regenS
    fi
    if [[ -n ${Queue} ]]; then 
	sed -i "/#PBS -q/c\#PBS -q ${Queue}" $regenS
    fi

fi



###########################
## === end of script === ##
###########################
