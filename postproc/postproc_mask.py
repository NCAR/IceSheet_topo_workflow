#!/usr/bin/env python

import sys, os
from numpy import *
from netCDF4 import *

###########################
#
# Update sub-gridscale roughness
# over Greenland
#
# Author: M. Lofverstrom
#         NCAR, Dec 18 2017
#
###########################

camRest  = Dataset(sys.argv[1],'r+')
topoDataIn  = Dataset(sys.argv[2],'r')
topoDataOut = Dataset(sys.argv[2],'r+')
c2t060   = Dataset(sys.argv[4],'r')
c2t008   = Dataset(sys.argv[5],'r')

gland_mask = Dataset(sys.argv[3],'r').variables['greenland_mask'][:]

####

phis_060 = c2t060.variables['PHIS'][:]
sgh30_060 = c2t060.variables['SGH30'][:]
sgh_008 = c2t008.variables['SGH'][:]

Field = 'SGH30'
topoDataOut.variables[Field][:] = where(gland_mask==1.,
                                        sqrt(sgh30_060**2+sgh_008**2),
                                        topoDataIn.variables[Field][:])

camRest.variables[Field][:] = where(gland_mask==1.,
                                    sqrt(sgh30_060**2+sgh_008**2),
                                    topoDataIn.variables[Field][:])

###

Field = 'PHIS'
topoDataOut.variables[Field][:] = where(gland_mask==1.,
                                        phis_060,
                                        topoDataIn.variables[Field][:])

camRest.variables[Field][:] = where(gland_mask==1.,
                                    phis_060,
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
