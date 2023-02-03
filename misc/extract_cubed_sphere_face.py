#!/usr/bin/env python
#
import os
from numpy import * 
import numpy.ma as ma
import matplotlib.pyplot as plt
from matplotlib import rcParams
from mpl_toolkits.basemap import Basemap
from netCDF4 import Dataset as NetCDFFile

###########################

class cubedSphereFace(object):
    def __init__(self,dataFile):

        self.fpin = NetCDFFile(infile,'r')
        self.tlat = self.fpin.variables['lat'][:]
        self.tlon = self.fpin.variables['lon'][:]

        ## Reshape 1D array as 3D array (3000,3000,6)
        self.nx = 3000
        self.ny = 3000
        self.nfaces = 6

        self.order = 'F'
        self.face = -1

        self.newDims = (self.ny,self.nx,self.nfaces)

        ## Issue with second dimension, hence the ::-1 construction
        self.lat = reshape(self.tlat,self.newDims,order=self.order)[:,::-1,self.face]
        self.lon = reshape(self.tlon,self.newDims,order=self.order)[:,::-1,self.face]
       

        ###

        self.fpin.close()


    def plotGrid(self,e=50):

        lat = self.lat[::e,::e]
        lon = self.lon[::e,::e]

        plt.figure(figsize=(12,12))
        plt.subplot(1,1,1)

        m = Basemap(projection='npstere',
                    boundinglat=30,
                    lon_0=270,
                    resolution='l')

        m.drawcoastlines()

        x, y = m(lon,lat)
        im = m.pcolor(x,y,
                      ma.masked_array(zeros(lat.shape,'f')),
                      antialiased=True, 
                      cmap=plt.cm.cool)

        plt.title('Cubed sphere gridcells')
        plt.show()



    def plotField(self,Field='terr',e=20):

        lat = self.lat[::e,::e]
        lon = self.lon[::e,::e]


        if Field == 'terr':  
            self.tterr = self.fpin.variables['terr'][:]
            self.terr = reshape(self.tterr,
                                self.newDims,
                                order=self.order)[:,::-1,self.face]
            var = self.terr[::e,::e]

        if Field == 'var30': 
            self.tvar30 = self.fpin.variables['var30'][:]
            self.var30 = reshape(self.tvar30,
                                 self.newDims,
                                 order=self.order)[:,::-1,face]
            var = self.var30[::e,::e]
        
#        print(amax(amax(var,axis=0),axis=0))


        plt.figure(figsize=(12,12))
        plt.subplot(1,1,1)

        m = Basemap(projection='cyl',
                    llcrnrlat=-90,
                    urcrnrlat=90,
                    llcrnrlon=0,
                    urcrnrlon=360,
                    resolution='c')

        boundinglat = 30
        if self.face == 6: boundinglat = 30


        m = Basemap(projection='npstere',
                    boundinglat=boundinglat,
                    lon_0=270,
                    resolution='l')

        x, y = m(lon,lat)
        m.drawcoastlines()

        im = m.pcolor(x,y,
                      var,
                      antialiased=True, 
                      cmap=plt.cm.jet,
                      )

        cbar = plt.colorbar(im)

        plt.show()



###########################

if __name__ == "__main__":

    dataPath =  os.getcwd()

    infile   = '%s/bin_to_cube/ncube3000.nc'%(dataPath)
    

    cs = cubedSphereFace(infile)
#    cs.plotGrid()
    cs.plotField(Field='terr')



###########################
print('Game Over!')
