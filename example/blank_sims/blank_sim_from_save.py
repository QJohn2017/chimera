import numpy as np
import sys, os,time
sys.path.append('./src/')
sys.path.append('./moduls/')
from mpi4py.MPI import COMM_WORLD as comm
from species import Specie
from solvers import Solver
from chimera_main import ChimeraRun
from chimera_tools import *
import cPickle as pickle
from RunRestart import StartFromSave
runsave = StartFromSave()
in_folder = '../' # define folder with save

def stack_overlapped(x):
	loc_arrays = []
	for i in xrange(len(x)-1):
		dat = x[i].copy()
		dat[:,-1] += x[i+1][:,0]
		dat = dat[:,1:]
		loc_arrays.append(dat)
	return np.concatenate(loc_arrays,axis=1)

fld_out_step = 100
dns_out_step = 100
phs_out_step = 1000

if sys.argv[-1]=='sim':
	solver = Solver(comm,solver_in)
	specie1 = Specie(comm,specie1_in)
	specie2 = Specie(comm,specie2_in)	# check used number of species
	chimera_in = {'Solvers':(solver,),'Particles':(specie1,specie2,),'MovingFrames':(MovingFrame,)}
	Chimera = ChimeraRun(comm,chimera_in)

	file2load = open(in_folder+'savedrun_'+str(comm.rank)+'.p','r')
	runload = pickle.load(file2load)
	runload.LoadRun(Chimera)
	Step2Start = runload.Step2Start

	if comm.rank==0:							#
		os.system('rm -rf '+out_folder)	# REMOVE IS in_folder AND out_folder ARE SAME
		os.system('mkdir ' +out_folder)	#

	timestart = time.time()
	if comm.rank==0:
		os.system('rm -rf '+out_folder)
		os.system('mkdir ' +out_folder)
	for i in xrange(Step2Start,Steps2Do):
		Chimera.make_step(i*dt)
		if comm.rank==0: print i
		if np.mod(i,fld_out_step)==0:
			ee = comm.gather(solver.EB[:,1:])
			if comm.rank==0:
				istr = str(i)
				while len(istr)<7: istr='0'+istr
				np.save(out_folder+'ee_'+istr+'.npy',np.concatenate(ee,axis=1))
		if np.mod(i,dns_out_step)==0:
			dens = comm.gather(specie1.get_dens_on_grid(solver_in['MaxAzimuthMode']))
			if comm.rank==0:
				istr = str(i)
				while len(istr)<7: istr='0'+istr
				if comm.size!=1:
					np.save(out_folder+'edens_'+istr+'.npy',stack_overlapped(dens))
				else:
					np.save(out_folder+'edens_'+istr+'.npy',np.concatenate(dens,axis=1))
		if np.mod(i,phs_out_step)==0:
			phs = comm.gather(specie1.particles)
			if comm.rank==0:
				istr = str(i)
				while len(istr)<7: istr='0'+istr
				np.save(out_folder+'phs'+istr+'.npy', np.concatenate(phs,axis=1))
	runsave.SaveRun(Chimera)
	runsave.Step2Start = i
	file2save = open(out_folder+'savedrun_'+str(comm.rank)+'.p','wb')
	pickle.dump(runsave, file2save, pickle.HIGHEST_PROTOCOL)
	if comm.rank==0: print 'done in %f minutes' % ((time.time()-timestart)/60.,)
