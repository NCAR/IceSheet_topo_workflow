;Jeremy Fyke
;03-07-13

load "$NCARG_ROOT/lib/ncarg/nclscripts/csm/gsn_code.ncl"
load "$NCARG_ROOT/lib/ncarg/nclscripts/csm/gsn_csm.ncl" 
load "$NCARG_ROOT/lib/ncarg/nclscripts/csm/contributed.ncl"

begin
  ;####Open i/o topography files(file names sent by command line arguments)
  GIS_topog = addfile(input_file_name,"r")
  usgs_topog = addfile(output_file_name,"w")

  ;####Load Greenland tiles of raw USGS topography and land fraction
  usgs_topog_tile = usgs_topog->htopo(16800:,32400:)
  usgs_landfract_tile = usgs_topog->landfract(16800:,32400:)

  ;#equivalent tile of ISM-derived topography and land fraction

  GIS_topo=doubletoint(GIS_topog->usrf(::-1,:))
  GIS_mask=floattoint(GIS_topog->landmask_float(::-1,:))

  ;####Merge topography and landmask from ISM-derived values, over island of Greenland
  ;ismissing(GIS_mask) returns 'true'  outside of GIS regions
  ;subsequent ingestion by 'where' sets the landfrac and topography values to the (original)
  ;values.  Where ismissing(GIS_mask) is false (i.e. the ISM-derived data exists), landfrac
  ;and topographies are set to the ISM values.
  
  usgs_landfract_tile= where( ismissing(GIS_mask), usgs_landfract_tile, GIS_mask )
  usgs_topog_tile=     where( ismissing(GIS_mask), usgs_topog_tile,     GIS_topo )

  ;####Insert altered topography and landmask back into full USGS dataset.
  usgs_topog->htopo(16800:,32400:)=usgs_topog_tile
  usgs_topog->landfract(16800:,32400:)=usgs_landfract_tile

end
