#!/usr/bin/env python
#########################################################################
##############          IMPORTS          ################################
#########################################################################

import numpy as np

import sys
import os, logging
logging.basicConfig(format='%(asctime)s | %(levelname)s : %(message)s',\
                     level=logging.INFO, stream=sys.stdout)
import time

import argparse

import gwnr.stats as SU
import gwnr.analysis as DA

from pycbc.pnutils import *
from glue import gpstime

from glue.ligolw import ligolw
from glue.ligolw import table
from glue.ligolw import lsctables
from glue.ligolw import ilwd
from glue.ligolw import utils as ligolw_utils
from glue.ligolw.utils import process as ligolw_process

PROGRAM_NAME = os.path.abspath(sys.argv[0])
__author__ = "Prayush Kumar <prayush@astro.cornell.edu>"

#########################################################################
#################### Input parsing #####################
#########################################################################
#{{{
parser = argparse.ArgumentParser(
    usage="%%prog [OPTIONS]",
    description="""
Takes in the iteration id. It chooses 'num-new-points' new points. Each of these
points are chosen in a way that they mchirp > (1+mw)*mchirp of all points in a
pre-existing "old_bank". This is done to ensure that these new points are
minimally overlapping in terms of the parameter space volume that they cover.
""",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)

# Sampling Parameters
parser.add_argument("--iteration-id",
                    dest="iid",
                    help="The index of the iteration",
                    type=int)
parser.add_argument("--num-new-points",
                    help="No of bank points in each sub-job",
                    default=1000,
                    type=int)
parser.add_argument("--max-attempts",
                    help="""Max out if these many attempts do not furnish a
viable new point""",
                    default=1e7,
                    type=int)

parser.add_argument("--old-bank",
                    help="""Old bank from which the new points should at least
be a mchirp_window away""",
                    default="",
                    type=str)

# Physical parameter ranges
parser.add_argument('--component-mass-min',
                    help="Minimum value allowed for component masses",
                    default=5.0,
                    type=float)
parser.add_argument('--component-mass-max',
                    help="Maximum value allowed for component masses",
                    default=50.0,
                    type=float)
parser.add_argument('--total-mass-max',
                    help="Maximum value allowed for total mass",
                    default=100.0,
                    type=float)

parser.add_argument('--spin-mag-min',
                    help="Minimum value allowed for component spin magnitudes",
                    default=0.0,
                    type=float)
parser.add_argument('--spin-mag-max',
                    help="Maximum value allowed for component spin magnitudes",
                    default=0.0,
                    type=float)

parser.add_argument(
    '--spin-component-min',
    help="Minimum value allowed for component spin x,y,z comps",
    default=0.0,
    type=float)
parser.add_argument(
    '--spin-component-max',
    help="Maximum value allowed for component spin x,y,z comps",
    default=0.0,
    type=float)

parser.add_argument('--eccentricity-min',
                    help="Minimum value allowed for eccentricity",
                    default=0.0,
                    type=float)
parser.add_argument('--eccentricity-max',
                    help="Maximum value allowed for eccentricity",
                    default=0.4,
                    type=float)

parser.add_argument('--inclination-min',
                    help="Minimum value allowed for inclination angle",
                    default=0.0,
                    type=float)
parser.add_argument('--inclination-max',
                    help="Maximum value allowed for inclination angle",
                    default=0.0,
                    type=float)

parser.add_argument('--coa-phase-min',
                    help="Minimum value allowed for reference phase",
                    default=0.0,
                    type=float)
parser.add_argument('--coa-phase-max',
                    help="Maximum value allowed for reference phase",
                    default=0.0,
                    type=float)

parser.add_argument('--mean-per-ano-min',
                    help="Minimum value allowed for mean periastron anomaly",
                    default=0.0,
                    type=float)
parser.add_argument('--mean-per-ano-max',
                    help="Maximum value allowed for mean periastron anomaly",
                    default=0.0,
                    type=float)

parser.add_argument(
    '--long-asc-nodes-min',
    help="Minimum value allowed for longitude of ascending nodes",
    default=0.0,
    type=float)
parser.add_argument(
    '--long-asc-nodes-max',
    help="Maximum value allowed for the longitude of ascending node",
    default=0.0,
    type=float)

# Sky location and orientation parameters
parser.add_argument('--latitude-min',
                    help="Minimum value allowed for latitude (or declination)",
                    default=0.0,
                    type=float)
parser.add_argument('--latitude-max',
                    help="Maximum value allowed for latitude (or declination)",
                    default=0.0,
                    type=float)

parser.add_argument(
    '--longitude-min',
    help="Minimum value allowed for longitude (or right ascension)",
    default=0.0,
    type=float)
parser.add_argument(
    '--longitude-max',
    help="Maximum value allowed for longitude (or right ascension)",
    default=0.0,
    type=float)

parser.add_argument('--polarization-min',
                    help="Minimum value allowed for polarization angle",
                    default=0.0,
                    type=float)
parser.add_argument('--polarization-max',
                    help="Maximum value allowed for polarization angle",
                    default=0.0,
                    type=float)

# Match parameters
parser.add_argument('-w',
                    '--mchirp-window',
                    metavar='MC_WIN',
                    dest="mchirp_window",
                    help="""Fractional window on mchirp parameter. If waveform
parameters differ by more than this window, the overlap is set to 0.""",
                    default=0.01,
                    type=float)
parser.add_argument('-e',
                    '--eccentricity-window',
                    metavar='E0_WIN',
                    dest="ecc_window",
                    help="""Absolute window on eccentricity.""",
                    default=0.0,
                    type=float)

# Others
parser.add_argument("--output-prefix",
                    help="""Prefix to the name of the new bank, formatted
finally as 'output_prefix' + '%%06d.xml'.""",
                    default="testpoints/test_",
                    type=str)

parser.add_argument("-C",
                    "--comment",
                    metavar="STRING",
                    help="add the optional STRING as the process:comment",
                    default='')
parser.add_argument("-V",
                    "--verbose",
                    action="store_true",
                    help="print extra debugging information",
                    default=False)

options = parser.parse_args()
#}}}
logging.info("mchirp-window = %f" % (options.mchirp_window))
logging.info("eccentricity-window = %f" % (options.ecc_window))
#ctx = CUDAScheme()

#########################################################################
################### Get new sample points ###############################
#########################################################################

################### Parameter Ranges ##################
mass_min = options.component_mass_min
mass_max = options.component_mass_max
eta_max = 0.25  # for mass_min + mass_min
mtotal_max = options.total_mass_max

smag_min = options.spin_mag_min
smag_max = options.spin_mag_max

sxyz_min = options.spin_component_min
sxyz_max = options.spin_component_max

ecc_min = options.eccentricity_min
ecc_max = options.eccentricity_max

mean_per_ano_min = options.mean_per_ano_min
mean_per_ano_max = options.mean_per_ano_max

long_asc_nodes_min = options.long_asc_nodes_min
long_asc_nodes_max = options.long_asc_nodes_max

coa_phase_min = options.coa_phase_min
coa_phase_max = options.coa_phase_max

inc_min = options.inclination_min
inc_max = options.inclination_max

dist_min = 1.e6
dist_max = 1.e6

pol_min = options.polarization_min
pol_max = options.polarization_max

lat_min = options.latitude_min
lat_max = options.latitude_max

lon_min = options.longitude_min
lon_max = options.longitude_max

mchirp_max = (2. * mass_max) * (eta_max**0.6)
mchirp_min = (2. * mass_min) * (eta_max**0.6)
mtotal_min = 2 * mass_min
eta_min = mass_max * mass_min / (mass_max + mass_min)**2.
q_min = 1.
q_max = DA.get_q_from_eta(eta_min)


#{{{
def sample_mass(N=1):
    return SU.uniform_CompactObject_mass(N, mass_min, mass_max)


def sample_mchirp(N=1):
    return SU.uniform_CompactObject_mass(N, mchirp_min, mchirp_max)


def sample_eta_uniform(N=1):
    return SU.uniform_CompactObject_massratio(N, eta_min, eta_max)


def sample_q_uniform(N=1):
    return SU.uniform_CompactObject_massratio(N, q_min, q_max)


def sample_smag(N=1):
    return SU.uniform_spin_magnitude(N, smag_min, smag_max)


def sample_sxyz(N=1):
    return SU.uniform_bound(sxyz_min, sxyz_max, N)


def sample_ecc(N=1):
    return SU.uniform_bound(ecc_min, ecc_max, N)


def sample_mean_per_ano(N=1):
    return SU.uniform_bound(mean_per_ano_min, mean_per_ano_max, N)


def sample_long_asc_nodes(N=1):
    return SU.uniform_bound(long_asc_nodes_min, long_asc_nodes_max, N)


def sample_coa_phase(N=1):
    return SU.uniform_bound(coa_phase_min, coa_phase_max, N)


def sample_inc(N=1):
    return SU.uniform_bound(inc_min, inc_max, N)


def sample_dist(N=1):
    return SU.uniform_in_volume_distance(N, dist_min, dist_max)


def sample_pol(N=1):
    return SU.uniform_bound(pol_min, pol_max, N)


def sample_lat_lon(N=1):
    if lat_min == lat_max or lon_min == lon_max:
        return SU.uniform_bound(lat_min, lat_max, N),\
               SU.uniform_bound(lon_min, lon_max, N)
    lat, lon = SU.CubeToUniformOnS2(np.random.uniform(0, 1, N),
                                    np.random.uniform(0, 1, N))
    while lat > lat_max or lat < lat_min or lon > lon_max or lon < lon_min:
        lat, lon = SU.CubeToUniformOnS2(np.random.uniform(0, 1, N),
                                        np.random.uniform(0, 1, N))
    return lat, lon


def get_sim_hash(N=1, num_digits=10):
    return ilwd.ilwdchar(":%s:0" %
                         DA.get_unique_hex_tag(N=N, num_digits=num_digits))


def accept_point_boundary(mc, eta):
    return True
    # The following function describes the equation of the boundary of the region
    # which bounds the BBH systems that have 100% of their power in <= 40 waveform
    # cyclces. (For non-spinning systems). Also taking only points with mchirp
    # below 52.233 to not sample the region which is already covered by the
    # bank_0.xml
    feta = -63.5 * eta**2 + 65.9 * eta + 19.7
    if mc >= feta and mc < 52.233:
        return True
    else:
        return False


def accept_point(mc, eta):
    m1, m2 = mchirp_eta_to_mass1_mass2(mc, eta)
    if m1 > mass_max or m1 < mass_min: return False
    if m2 > mass_max or m2 < mass_min: return False
    if (m1 + m2) > mtotal_max or (m1 + m2) < mtotal_min: return False
    return True


################### Functions to sample & reject ##################
def get_new_sample_point():
    """This function returns an instance of lsctables.SimInspiral, with elements
  corresponding to various physical parameters uniformly sampled within their
  respective ranges. """
    p = lsctables.SimInspiral()

    # Masses
    p.mchirp = sample_mchirp()
    p.eta = sample_eta_uniform()
    while not accept_point(p.mchirp, p.eta):
        p.mchirp = sample_mchirp()
        p.eta = sample_eta_uniform()
    p.mass1, p.mass2 = mchirp_eta_to_mass1_mass2(p.mchirp, p.eta)

    # Spins
    p.spin1x = sample_sxyz()
    p.spin1y = sample_sxyz()
    p.spin1z = sample_sxyz()
    smag = np.sqrt(p.spin1x**2. + p.spin1y**2. + p.spin1z**2.)
    if smag > smag_max or smag < smag_min:
        newsmag = sample_smag()
        p.spin1x *= (newsmag / smag)
        p.spin1y *= (newsmag / smag)
        p.spin1z *= (newsmag / smag)

    p.spin2x = sample_sxyz()
    p.spin2y = sample_sxyz()
    p.spin2z = sample_sxyz()
    smag = np.sqrt(p.spin2x**2. + p.spin2y**2. + p.spin2z**2.)
    if smag > smag_max or smag < smag_min:
        newsmag = sample_smag()
        p.spin2x *= (newsmag / smag)
        p.spin2y *= (newsmag / smag)
        p.spin2z *= (newsmag / smag)

    # Orbital parameters
    p.alpha = sample_ecc()
    p.alpha1 = sample_mean_per_ano()
    p.alpha2 = sample_long_asc_nodes()
    p.coa_phase = sample_coa_phase()

    # Orientation and location
    p.inclination = sample_inc()
    p.distance = sample_dist()

    # Polarization
    p.polarization = sample_pol()

    # Sky angles
    p.latitude, p.longitude = sample_lat_lon()

    # Unique HASH
    p.simulation_id = get_sim_hash()

    # Process ID
    p.process_id = out_proc_id
    return p


def within_mchirp_window(bank, sim, w):
    #{{{
    if hasattr(bank, "mchirp"):
        bmchirp = bank.mchirp
    elif hasattr(bank, "mass1") and hasattr(bank, "mass2"):
        bmchirp, eta = mass1_mass2_to_mchirp_eta(bank.mass1, bank.mass2)
    elif hasattr(bank, "mtotal") and hasattr(bank, "eta"):
        bmchirp = bank.mtotal * (bank.eta**0.6)

    if hasattr(sim, "mchirp"):
        smchirp = sim.mchirp
    elif hasattr(sim, "mass1") and hasattr(sim, "mass2"):
        smchirp, eta = mass1_mass2_to_mchirp_eta(sim.mass1, sim.mass2)
    elif hasattr(sim, "mtotal") and hasattr(sim, "eta"):
        smchirp = sim.mtotal * (sim.eta**0.6)

    if abs(smchirp - bmchirp) < (w * min(smchirp, bmchirp)):
        return True
    return False
    #}}}


def within_ecc_window(bank, sim, w):
    if np.abs(sim.alpha - bank.alpha) < w:
        return True
    return False


def reject_new_sample_point(new_point,
                            points_table,
                            in_mchirp_window,
                            ecc_window=0.0):
    """This function takes in a new proposed point, and finds its mchirp distance
  with all points in the points_table. If all of these distances are >
  in_mchirp_window, it returns True, else returns False.
  Which implies that if the new proposed point should be rejected from the set,
  it returns True, and False if that point should be kept."""
    if in_mchirp_window:
        mchirp_window = in_mchirp_window
    else:
        mchirp_window = 0.0

    for point in points_table:
        if within_mchirp_window(new_point, point,
                                mchirp_window) and within_ecc_window(
                                    new_point, point, ecc_window):
            return True

    return False


#}}}

#####################################################
########## Obtain & Save new sample points ##########
#####################################################

######## Reading old points file ############
old_points_name = options.old_bank
if not os.path.exists(old_points_name):
    old_points_table = []
else:
    indoc = ligolw_utils.load_filename(old_points_name,
                                       contenthandler=table.use_in(
                                           ligolw.LIGOLWContentHandler),
                                       verbose=options.verbose)
    try:
        old_points_table = lsctables.SimInspiralTable.get_table(indoc)
    except:
        raise IOError("Please provide the old bank as a SimInspiralTable")

######## Creating the new points file ############
#{{{
if options.iid is not None:
    iid = options.iid
    new_file_name = options.output_prefix + "%06d.xml" % iid
else:
    idx = 0
    name1 = options.output_prefix + "%06d.xml" % idx
    idx += 1
    name2 = options.output_prefix + "%06d.xml" % idx
    while os.path.exists(name2):
        if options.verbose:
            logging.info("trying name.. " + name1 + name2)
        idx += 1
        name1 = name2
        name2 = options.output_prefix + "%06d.xml" % idx
    new_file_name = name1
    iid = idx - 1
    logging.info(
        "Changing to iid = {}, all previous testpoints exist.".format(iid))
logging.info("Storing the new sample points in {}".format(new_file_name))
sys.stdout.flush()

new_points_doc = ligolw.Document()
new_points_doc.appendChild(ligolw.LIGO_LW())

out_proc_id = ligolw_process.register_to_xmldoc(
    new_points_doc, PROGRAM_NAME, options.__dict__,
    comment=options.comment).process_id

new_points_table = lsctables.New(lsctables.SimInspiralTable,columns=[\
  'mass1','mass2','mchirp','eta',\
  'spin1x','spin1y','spin1z','spin2x','spin2y','spin2z',\
  'alpha', # -> eccentricity
'alpha1', # -> mean_per_ano = meanPerAno
'alpha2', # -> long_asc_nodes = longAscNodes
'coa_phase',\
  'inclination','distance',\
  'polarization','latitude','longitude',\
  'simulation_id','process_id'])
new_points_doc.childNodes[0].appendChild(new_points_table)

#{{{
num_new_points = np.int(options.num_new_points)

break_now = False
cnt = 0
while cnt < num_new_points:
    if options.verbose:
        if cnt % (num_new_points / 50) == 0:
            logging.info("%d points chosen" % cnt)
    if cnt == 0:
        new_point = get_new_sample_point()
        new_points_table.append(new_point)
        cnt += 1
        continue

    k = 0
    new_point = get_new_sample_point()
    while reject_new_sample_point(new_point,\
                                  new_points_table,\
                                  options.mchirp_window,\
                                  options.ecc_window) or\
          (len(old_points_table) > 0 and\
          reject_new_sample_point(new_point,\
                                  old_points_table,\
                                  options.mchirp_window,\
                                  options.ecc_window)):
        if options.verbose and k % (num_new_points / 50) == 0:
            logging.info("\t\t ...rejecting sample %d" % k)
            sys.stdout.flush()
        k += 1
        new_point = get_new_sample_point()
        if k > options.max_attempts:
            break_now = True
            break  # Max out at 1,000,000 attempts to find a point!

    new_points_table.append(new_point)
    cnt += 1
    if break_now:
        logging.info("ONLY FILLED IN {} POINTS IN REASONABLE TIME.".format(
            len(new_points_table)))
        break

#}}}
############## Write the new sample points to XML #############
logging.info("Writing %d new points to %s" %
             (len(new_points_table), new_file_name))
sys.stdout.flush()

new_points_proctable = table.get_table(new_points_doc,
                                       lsctables.ProcessTable.tableName)
new_points_proctable[0].end_time = gpstime.GpsSecondsFromPyUTC(time.time())
ligolw_utils.write_filename(new_points_doc, new_file_name)
