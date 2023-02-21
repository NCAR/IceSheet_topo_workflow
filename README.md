# IceSheet_topo_workflow
Scripts to update CAM topography fields during a model run to include changes from interactive Ice Sheet models (CISM currently). This code and script bundle will update the CAM restart file with new PHIS and SGS30 large and sub-grid scale topography only around the Greenland Ice Sheet. It also generates a new topography file with updates only around the Greenland Ice Sheet for use in the run. 

Instructions below describe how to use the CESM workflow tools to set up an automatically scheduled topography updating job inbetween CESM 10 year long run segments. This is the workflow used in many large fully-coupled CESM experiements with active ice sheets.

-- Last updated Feb 21, 2023


## CISM Topography Updating Workflow

**These instructions require CESM 2.1.1 or greater.**

1. Edit your ``config_workflow.xml`` file. This is found in ``cime/config/cesm/machines`` for CESM 2.1 and early 2.2. More recent CESM versions keep this file in ``ccs_config/machines/`` . You will need to add the following code to this file anywhere after a ``</workflow_jobs>`` tag but before the ``</config_workflow>`` tag at the end of the file. 
```
  <workflow_jobs id="topo_regen_10yr_cycle">
    <!-- order matters, jobs will be run in the order listed here -->
    <job name="case.run">
      <template>template.case.run</template>
      <prereq>$BUILD_COMPLETE and not $TEST</prereq>
    </job>
    <job name="case.test">
      <template>template.case.test</template>
      <prereq>$BUILD_COMPLETE and $TEST</prereq>
    </job>
    <job name="case.topo_regen">
      <template>$EXEROOT/../run/dynamic_atm_topo/template.topo_regen</template>
      <!-- If case.run (or case.test) exits successfully then run topo_regen-->
      <dependency>case.run or case.test</dependency>
      <prereq>1</prereq>
      <runtime_parameters>
        <task_count>1</task_count>
        <tasks_per_node>1</tasks_per_node>
        <walltime>0:45:00</walltime>
      </runtime_parameters>
    </job>
    <job name="case.st_archive">
      <template>template.st_archive</template>
      <!-- If case.topo_regen exits successfully then run st_archive-->
      <dependency>case.topo_regen</dependency>
      <prereq>$DOUT_S</prereq>
      <runtime_parameters>
        <task_count>1</task_count>
        <tasks_per_node>1</tasks_per_node>
        <walltime>0:20:00</walltime>
      </runtime_parameters>
    </job>
  </workflow_jobs>
```

2. Create your case. When you create your case you will need to add the flag ``--workflow topo_regen_10yr_cycle`` . For example:
```
     ./create_newcase --case Test_topo_regen_workflow_m03 --compset B1850G --res f09_g17_gris4 --workflow topo_regen_10yr_cycle --project P93300606 --run-unsupported
```

3. Go into your new case directory and run ``./case.setup`` you should see a warning that says "Input template file /glade/scratch/katec/Test_topo_regen_workflow_m03/bld/../run/dynamic_atm_topo/template.topo_regen for job case.topo_regen does not exist or cannot be read." If you don't see a warning like this for your case than something has gone wrong. Check that you did the first two steps correctly.

4. If you do get the warning, now it's time to get the topography updating tools. Go to your run directory (so, for the above example case, ``cd /glade/scratch/user/Test_topo_regen_workflow_m03/run`` and in that directory type:
```
     > git clone https://github.com/NCAR/IceSheet_topo_workflow.git dynamic_atm_topo 
```

This will checkout the topography updater into the "dynamic_atm_topo" subdirectory.

5. Now type ``cd dynamic_atm_topo/bin_to_cube`` and type ``make``. This will build that tool. When it's done type ``cd ../cube_to_target`` and type ``make``. This will build the other tool.

6. Go back to your case directory. Type ``./case.setup --reset`` and now you should see it say:
```
     Writing case.topo_regen script from input template /glade/scratch/user/Test_topo_regen_workflow_m04/bld/../run/dynamic_atm_topo/template.topo_regen

     Creating file .case.topo_regen
```

7. Build your case (type ``qcmd -- ./case.build`` on Cheyenne)

8. Change your run parameters. This workflow will have the topography updater run after each successful case.run segment. So, if your segments are 5 years, then the topography will update every 5 years. Previous experiments were run with 10 year segments and the topography updated every 10 years. So, basically the pattern was:

*Run for 10 years, Update Topography, Short Term Archiver*

To get this you would need to do these xml commands:
```
  ./xmlchange STOP_N = 10
  ./xmlchange STOP_OPTION=nyears
  ./xmlchange REST_N = 10
  ./xmlchange REST_OPTION=nyears
  ./xmlchange RESUBMIT=9
```

That will run for 10 segments of 10 years or 100 years with the topography updating every 10 years.

9. Submit your run (type ``./case.submit``). You should see three jobs fired off at the same time. Your run job should be queued and then the topography and archive jobs should be holding in the queue waiting for the completion of the run script.

10. After each segment is complete, you should see a ``topo_regen.log`` file in your case directory. You can give those a quick look-through to make sure that the script ran successfully. The script updates the topography file in the run directory and the cam restart file PHIS field. The restart with the updated field is archived. So, you can go through your restarts and plot the PHIS field to make sure the atmosphere is seeing the evolving topography.


