load "$NCARG_ROOT/lib/ncarg/nclscripts/csm/gsn_code.ncl"
load "$NCARG_ROOT/lib/ncarg/nclscripts/csm/gsn_csm.ncl"
load "$NCARG_ROOT/lib/ncarg/nclscripts/csm/contributed.ncl"
load "$NCARG_ROOT/lib/ncarg/nclscripts/esmf/ESMF_regridding.ncl"

begin
;******************** USER DEFINED VARIABLES***********************

  ; included as an attribute in the output
  input_title="Generated from ISM curvilinear grid"

  ; input data are curvilinear, so lat & lon are specified by 2-d
  ; arrays, as given here:
  lat_var_name="lat"
  lon_var_name="lon"

  ; is the input a regional file? (as opposed to a global file)
  input_is_regional = True

  source_large_file = False

  template_file_name="template_out.nc"

  template_var_name="ice_shelf"

  ; is the template a regional file? (as opposed to a global file)
  template_is_regional = True

  dest_large_file = True

  wgt_large_file = True

  interp_method = "bilinear"

  ; set the following to true if the necessary files have already been
  ; generated
  skip_src_grid = True
  skip_dst_grid = True
  skip_wgt_gen = True

;*****************END OF USER DEFINED VARIABLES*******************

;************************************************
; Get template longitudes and latitudes
;************************************************

  template_file = addfile(template_file_name, "r")
  template_var = template_file->$template_var_name$
  dsizes = dimsizes(template_var)
  rank = dimsizes(dsizes)  ; number of dimensions
  
  template_lon_name = template_var!(rank-1)
  template_lat_name = template_var!(rank-2)
  template_lon = template_var&$template_lon_name$
  template_lat = template_var&$template_lat_name$
  
;************************************************
; Read in input file (not individual variables, yet)
;************************************************
  
  input_file = addfile(input_file_name, "r")

;************************************************
; Set regridding options
;************************************************

  Opt = True

  Opt@SrcGridLat = input_file->$lat_var_name$
  Opt@SrcGridLon = input_file->$lon_var_name$
  Opt@SrcRegional = input_is_regional
  Opt@SrcLargeFile = source_large_file
; according to the documentation, DstGridType shouldnt be required,
; but it seems to be
  Opt@DstGridType = "rectilinear"
  Opt@DstGridLat = template_lat
  Opt@DstGridLon = template_lon
  Opt@DstRegional = template_is_regional
  Opt@DstLargeFile = dest_large_file
  Opt@LargeFile = wgt_large_file

  Opt@InterpMethod = interp_method

  Opt@SrcFileName = "source_grid_file.nc"
  Opt@DstFileName = "destination_grid_file.nc"
  Opt@WgtFileName = "weights_file.nc"
  Opt@SkipSrcGrid = skip_src_grid
  Opt@SkipDstGrid = skip_dst_grid
  Opt@SkipWgtGen = skip_wgt_gen

  Opt@SrcInputFileName=input_file_name
  Opt@SrcTitle=input_title
  Opt@CopyVarCoords = True
  Opt@ForceOverwrite = True
  Opt@Debug = True

  ; Main Regridding:
  ; Regrid variables, outputting interpolated version file

  GIS_topog = input_file->thk + input_file->topg
  GIS_topog = where(GIS_topog.lt.0., 0., GIS_topog)
  landmask_float = new(dimsizes(GIS_topog),float,-9999.)
  landmask_float = where (GIS_topog.gt.0., 1, landmask_float)
  
  tmp = doubletoint(ESMF_regrid(GIS_topog,Opt))
  GIS_topog_regridded = tmp(::-1,:)
  delete(tmp)
  ; after the first variable, we can skip some steps in regridding
  ; the other variables; this is done via the following options:
  Opt@SkipSrcGrid = True
  Opt@SkipDstGrid = True
  Opt@SkipWgtGen = True  
  tmp = floattoint(ESMF_regrid(landmask_float,Opt))
  landmask_float_regridded = tmp(::-1,:)
  delete(tmp)  
  
  ; Save regridded tile to an archived reference file
  print ("Save regridded tile to an archived reference file")
  archive_file = addfile("ISM30sec.archived.nc","c")
  archive_file->usrf = GIS_topog_regridded
  archive_file->landmask_float = landmask_float_regridded
  

  usgs_topog_file     = addfile(global_file_name,"w")
  usgs_topog_tile     = usgs_topog_file->htopo(16800:,32400:)
  usgs_landfract_tile = usgs_topog_file->landfract(16800:,32400:)
   
  ;####Merge topography and landmask from ISM-derived values, over island of Greenland
  ;ismissing(GIS_mask) returns 'true'  outside of GIS regions
  ;subsequent ingestion by 'where' sets the landfrac and topography values to the (original)
  ;values.  Where ismissing(GIS_mask) is false (i.e. the ISM-derived data exists), landfrac
  ;and topographies are set to the ISM values.
  
  print ("Replace missing values: landfrac")
  usgs_landfract_tile= where( ismissing(landmask_float_regridded), usgs_landfract_tile, landmask_float_regridded)
  print ("Replace missing values: topography")
  usgs_topog_tile=     where( ismissing(landmask_float_regridded), usgs_topog_tile, GIS_topog_regridded)  

  ;####Insert altered topography and landmask back into full USGS dataset.
;  print ("Insert altered topography back into full USGS dataset")
;  usgs_topog_file->htopo(16800:,32400:)=usgs_topog_tile
;  print ("Insert altered landmask back into full USGS dataset")
;  usgs_topog_file->landfract(16800:,32400:)=usgs_landfract_tile


  print ("Save regridded tile to file")
  archive_file= addfile(output_file_name,"c")
  archive_file->htopo = usgs_topog_tile
  archive_file->landfract = usgs_landfract_tile

end
