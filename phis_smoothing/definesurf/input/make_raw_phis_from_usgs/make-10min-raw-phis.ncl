  fname_out = "10min-phis-raw.nc"

  ftarget   = addfile ("10min-usgs-fv.nc", "r")
  fusgs     = addfile("highRes-rawdata.nc","r")
;  fusgs     = addfile("usgs-rawdata.nc","r")
  h = fusgs->htopo
  l = fusgs->landfract  

  printVarSummary( h )
  
  lon = ftarget->lon
  lat = ftarget->lat

  htopo  = area_hi2lores (h&lon,h&lat, h , True, 1,  lon, lat, True)  ; (ntim,49,120)
  ftopo  = area_hi2lores (l&lon,l&lat, l , True, 1,  lon, lat, True)  ; (ntim,49,120)

  system("/bin/rm -f " + fname_out)
  fout = addfile (fname_out, "c")

  htopo!0   = "lat"
  htopo&lat = lat 
  htopo!1   = "lon"
  htopo&lon = lon 

  ftopo!0   = "lat"
  ftopo&lat = lat
  ftopo!1   = "lon"
  ftopo&lon = lon

  fout->lon=lon
  fout->lat=lat
  fout->htopo=htopo
  fout->ftopo=ftopo
