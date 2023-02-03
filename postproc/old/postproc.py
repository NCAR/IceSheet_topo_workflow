#!/usr/bin/env python

import sys,os
from netCDF4 import Dataset
from numpy import *

###########################
#
# Replace SGH30 with "average" 
# SGH and SGH30 from smoothed
# fields
#
# Author:
# M. Lofverstrom
# April 14 2017
#
###########################
#
# To do:
# -- Add support for FV2 degree CESM2
#
###########################

camRest   = Dataset(sys.argv[1],'r')
smooth060 = Dataset(sys.argv[2],'r')
smooth008 = Dataset(sys.argv[3],'r')

#os.system('cp %s %s'%(sys.argv[2],sys.argv[4]))
outFile   = Dataset(sys.argv[4],'a')

###

## Get variables from restart dataset
phisR  = camRest.variables['PHIS'][:] 
sghR   = camRest.variables['SGH'][:] 
sgh30R = camRest.variables['SGH30'][:] 

## Get grid information
lat = camRest.variables['lat'][:]
lon = camRest.variables['lon'][:]

ny = len(lat)
nx = len(lon)

if    ny == 192 and nx == 288: grid = 'FV1'
elif  ny == 96  and nx == 144: grid = 'FV2'
else: print 'Not a supported grid resolution (%s,%s)'%(ny,nx)

## Get variables from smoothed files
phis  = smooth060.variables['PHIS'][:]
sgh30 = smooth060.variables['SGH30'][:]
sgh   = smooth008.variables['SGH'][:]
landf = smooth008.variables['LANDFRAC'][:]

###

sgh2 = sqrt(sgh**2 + sgh30**2)
sgh30x = copy(sgh30)
sghx   = copy(sgh)
phisx  = copy(phis)*0.



go = False
if grid == 'FV1':
    sy = 158; ey = 185
    sx = 235; ex = 278
    go = True

if grid == 'FV2':
    sy = 0; ey = ny
    sx = 0; ex = nx
    go = True

if go is True:
    for ix in range(sx,ex):
        for iy in range(sy,ey):
            if landf[iy,ix] > .1:
                sgh30x[iy,ix] = sgh2[iy,ix]
                sghx[iy,ix]   = sgh[iy,ix]
                phisx[iy,ix]  = phis[iy,ix]


## Fix Iceland
go = False
if grid == 'FV1':
    sy = 162; ey = 167
    sx = 267; ex = 278
    go = True
    
if grid == 'FV2':
    sy = 0; ey = ny
    sx = 0; ex = nx
    go = True

if go is True:
    for ix in range(sx,ex):
        for iy in range(sy,ey):
            if landf[iy,ix] > .1:
                sgh30x[iy,ix] = sgh30[iy,ix]
                sghx[iy,ix]   = sghR[iy,ix]
                phisx[iy,ix]  = phisR[iy,ix]


## Fix Baffin Island
go = False
if grid == 'FV1':
    sy = 157; ey = 168
    sx = 230; ex = 240
    go = True

if grid == 'FV2':
    sy = 0; ey = ny
    sx = 0; ex = nx
    go = True

if go is True:
    for ix in range(sx,ex):
        for iy in range(sy,ey):
            if landf[iy,ix] > .1:
                sgh30x[iy,ix] = sgh30[iy,ix]
                sghx[iy,ix]   = sghR[iy,ix]
                phisx[iy,ix]  = phisR[iy,ix]


sgh2 = sgh30x

###

phisO  = where(phisx>0.,phisx,phisR)
sghO   = where(sghx>0.,sghx,sghR)
sgh30O = where(sgh2>0.,sgh2,sgh30R)

outFile.variables['PHIS'][:]  = phisO[:]
outFile.variables['SGH'][:]   = sghO[:]
outFile.variables['SGH30'][:] = sgh30O[:]

outFile.close()


###########################
## === end of script === ##
###########################
