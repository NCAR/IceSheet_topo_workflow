#!/usr/bin/env python

import sys
from numpy import *
from netCDF4 import *

###########################
#
# Merge fields from cube_to_target 
# into one dataset
#
# Author: M. Lofverstrom
#         NCAR, Dec 18 2017
#
###########################

#outFile  = Dataset(sys.argv[1],'a')
camRest  = Dataset(sys.argv[1],'r+')
topoDataIn  = Dataset(sys.argv[2],'r')
topoDataOut = Dataset(sys.argv[2],'r+')
c2t060   = Dataset(sys.argv[4],'r')
c2t008   = Dataset(sys.argv[5],'r')

gland_mask = Dataset(sys.argv[3],'r').variables['greenland_mask'][:]

####

c2t060_vars_exclude = ['lat','lon','LANDM_COSLAT','SGH']
c2t060_vars_camRest = ['PHIS','SGH30']
c2t008_vars         = ['SGH']


## Process fields from 60-point smoothing radius
for Field in c2t060.variables.keys():
    if Field not in c2t060_vars_exclude:
        topoDataOut.variables[Field][:] = where(gland_mask==1.,
                                                c2t060.variables[Field][:],
                                                topoDataIn.variables[Field][:])   

    if Field in c2t060_vars_camRest:
        camRest.variables[Field][:] = where(gland_mask==1.,
                                            c2t060.variables[Field][:],
                                            topoDataIn.variables[Field][:])   


## Process fields from 8-point smoothing radius
for Field in c2t008_vars:
    topoDataOut.variables[Field][:] = where(gland_mask==1.,
                                            c2t008.variables[Field][:],
                                            topoDataIn.variables[Field][:])

    camRest.variables[Field][:] = where(gland_mask==1.,
                                        c2t008.variables[Field][:],
                                        topoDataIn.variables[Field][:])
###

camRest.close()
topoDataOut.close()


###########################

if __name__ == "__main":
    pass

###########################
## === end of script === ##
###########################
