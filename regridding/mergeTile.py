#!/usr/bin/env python

import sys
from netCDF4 import *

###########################

full = Dataset(sys.argv[1],'a')
tile = Dataset(sys.argv[2],'r')

for Field in ['htopo','landfract']:
    print('\nInserting modified %s in high resolution dataset'%Field)
    full.variables[Field][16800:,32400:] = tile.variables[Field][:,:]

full.close()
tile.close()

print('\n-> High resolution dataset updated successfully\n')

## === end of script === ##
