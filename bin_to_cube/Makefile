EXEDIR = .
EXENAME = bin_to_cube
RM = rm

.SUFFIXES:
.SUFFIXES: .F90 .o

DEBUG = FALSE

# Check for the NetCDF library and include directories 
ifeq ($(LIB_NETCDF),$(null))
LIB_NETCDF := /usr/local/lib
endif

ifeq ($(INC_NETCDF),$(null))
INC_NETCDF := /usr/local/include
endif

# Determine platform 
UNAMES := $(shell uname -s)
UNAMEM := $(findstring CRAY,$(shell uname -m))


#------------------------------------------------------------------------
# Linux
#------------------------------------------------------------------------

ifeq ($(UNAMES),Linux)
ifeq ($(USER_FC),$(null))
FC := ifort
FFLAGS = -c -g -r8 -O1 -I$(INC_NETCDF)
else
FC := $(USER_FC)
endif
LDFLAGS = -L$(LIB_NETCDF) -lnetcdf

.F90.o:
	$(FC) $(FFLAGS) $<
endif
#------------------------------------------------------------------------
# Default rules and macros
#------------------------------------------------------------------------

OBJS := bin_to_cube.o shr_kind_mod.o

$(EXEDIR)/$(EXENAME): $(OBJS)
	$(FC) -o $@ $(OBJS) $(LDFLAGS)

clean:
	$(RM) -f $(OBJS)  *.mod $(EXEDIR)/$(EXENAME)

bin_to_cube.o: shr_kind_mod.o
