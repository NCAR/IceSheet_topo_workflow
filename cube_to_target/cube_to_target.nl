&topoparams
  grid_descriptor_fname           = '/glade/p/cesm/liwg/cam_dyn_topog_data/fv_0.9x1.25.nc'
  output_grid                     = 'fv_0.9x1.25'
  intermediate_cubed_sphere_fname = '/glade/scratch/katec/Test_topo_regen_workflow_01/run/dynamic_atm_topog/bin_to_cube/ncube3000.nc'
  output_fname                    = 'junk'
  externally_smoothed_topo_file   = 'junk'
  lsmooth_terr = .false.
  lexternal_smooth_terr = .false.
  lzero_out_ocean_point_phis = .false.
  lzero_negative_peaks = .true.
  lsmooth_on_cubed_sphere = .true.
  ncube_sph_smooth_coarse = 8
  ncube_sph_smooth_fine = 1
  ncube_sph_smooth_iter = 1
  lfind_ridges = .false.
  lridgetiles = .false.
  nwindow_halfwidth = 42
  nridge_subsample = 8
  lread_smooth_topofile = .true.
/
