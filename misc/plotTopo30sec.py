#!/usr/bin/env python

import os,sys
from numpy import *
from netCDF4 import *
from scipy import interpolate
from plotObj import *

###########################


class dataServer:
    def __init__(self,dataFile):
        self.data = Dataset(dataFile,'r')

    def getVar(self,Field):
        return self.data.variables[Field][:]

    def varKeys(self):
        print(self.data.variables.keys())

    def getLatIdx(self,lat,lat0):
        return abs(lat-lat0).argmin()

    def getLonIdx(self,lon,lon0):
        return abs(lon-lon0).argmin()



def plotData(read=False,topo=None,lat=None,lon=None):
    
    print('--> plotData()')

    e = 100

    if read is True:
        lat = data.getVar('lat')[iy0:iy1:e]
        lon = data.getVar('lon')[ix0:ix1:e]
        topo = data.getVar('htopo')[iy0:iy1:e,ix0:ix1:e]


    pp = plotObj(lat,lon)

#    pp.cmapType = 'YlGnBu'
    pp.cmapType = 'RdYlGn'

    pp.levels = [250.,500.,750.,1000.,1250.,1500.,
                 1750.,2000.,2250.,2500.,2750.,
                 3000.,3250.,3500.,3750.,4000.,4250.,
                 4500.,4750.,5000.]

#    pp.levels = linspace(250.,5000.,20)



    pp.maxValue = pp.levels[-1]
    pp.minValue = pp.levels[0]

    pp.overColor = 'k'
    pp.underColor = 'w'

    pp.cbarTicks = pp.levels
    pp.contourLevs = pp.levels

#    pp.contourf(topo)
    pp.customContourfPlot(topo,lon,lat)

    pp.showFigure()



###########################

if __name__ == "__main__":

    res30sec = False
    resFV1   = False

    res30sec = True



    dataPath = '/glade/u/home/marcusl/work/dynamic_atm_topog_implement_Julio/dynamic_atm_topog/regridding'
    dataFile = '%s/modified-highRes.nc'%(dataPath)


    data = dataServer(dataFile)



    iy0 = 16800
    iy1 = -1
    
    ix0 = 32400
    ix1 = -1


    plotData(read=True)

###########################
    print('Game Over!')
## === end of script === ##
