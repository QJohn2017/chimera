import numpy as np
from inspect import getargspec
from cox_transport import *
import chimera.moduls.fimera as chimera

class Specie:
	def __init__(self,PartSpcs):
		self.Configs = PartSpcs
		if 'Features' not in self.Configs: self.Configs['Features'] = ()

		leftX, rightX,lengthR, dx, dr = self.Configs['Grid']

		if 'Xchunked' in self.Configs:
			from os import environ
			nthrds = int(environ['OMP_NUM_THREADS'])
			Nx = int(np.round(0.5/dx*(rightX - leftX)/nthrds)*2*nthrds)
		else:
			Nx = int(np.round(0.5/dx*(rightX - leftX))*2)

		Nr = int(np.round(lengthR/dr))
		Rgrid = dr*(np.arange(Nr)-0.5)
		Xgrid  = rightX - dx*np.arange(Nx)[::-1]
		leftX = Xgrid[0]

		if 'FixedCell' in self.Configs:
			self.Num_p = np.prod(self.Configs['FixedCell'])
			packX, packR, packO = np.mgrid[\
			  1:self.Configs['FixedCell'][0]:self.Configs['FixedCell'][0]*1j,\
			  1:self.Configs['FixedCell'][1]:self.Configs['FixedCell'][1]*1j,\
			  1:self.Configs['FixedCell'][2]:self.Configs['FixedCell'][2]*1j]
			packX = np.asfortranarray( (packX.ravel()-0.5)/self.Configs['FixedCell'][0])
			packR = np.asfortranarray( (packR.ravel()-0.5)/self.Configs['FixedCell'][1])
			packO = np.asfortranarray( np.exp(2.j*np.pi*(packO.ravel()-1.)/self.Configs['FixedCell'][2]) )
			self.Pax = (packX,packR,packO)
		elif 'RandCell' in self.Configs:
			self.Num_p = np.prod(self.Configs['RandCell'])
			self.Pax = lambda: (
			  np.random.rand(self.Num_p),\
			  np.random.rand(self.Num_p),\
			  np.exp(2.j*np.pi*np.random.rand(self.Num_p)))

		self.push_fact = 2*np.pi*self.Configs['Charge']/self.Configs['Mass']
		self.wght0 = self.Configs['Charge']*self.Configs['Density']*dr*dx*2*np.pi/self.Num_p

		self.Args = {'Nx':Nx,'Nr':Nr,'Xgrid':Xgrid,'Rgrid':Rgrid,'leftX':leftX,'rightX':rightX,\
		  'lowerR':(Rgrid*(Rgrid>=0)).min(),'upperR':Rgrid.max(),'dx':dx,'dr':dr,'NpSlice':Nx*self.Num_p}

		if 'MomentaMeans' not in self.Configs:
			self.Configs['MomentaMeans'] = (0.0,0.0,0.0)
		if 'MomentaSpreads' not in self.Configs:
			self.Configs['MomentaSpreads'] = (0.0,0.0,0.0)

		if 'Devices' in self.Configs:
			self.Devices = self.Configs['Devices']
		else:
			self.Devices = ()

		self.particles = np.zeros((8,0),order='F')
		self.particles_cntr = np.zeros((3,0),order='F')
		self.EB = np.zeros((6,0),order='F')

	def gen_parts(self,Domain = None,Xsteps=None,ProfileFunc=None):
		Xgrid = self.Args['Xgrid']
		Rgrid = self.Args['Rgrid']

		if Domain!=None:
			parts_left, parts_right,parts_rad0,parts_rad1 = Domain
			if self.Args['leftX']>parts_right or self.Args['rightX']<parts_left or parts_rad1<self.Args['lowerR'] \
			  or parts_rad0>self.Args['upperR']: return np.zeros((8,0))

		if Domain!=None:
			ixb,ixe = (Xgrid<parts_left).sum(),(Xgrid<parts_right).sum()+1
			Xgrid = Xgrid[ixb:ixe]
			if parts_rad0<=Rgrid.min():
				irb=0
			else:
				irb=(Rgrid<parts_rad0).sum()-1
			if parts_rad1>=Rgrid.max():
				ire = Rgrid.shape[0]
			else:
				ire = (Rgrid<parts_rad1).sum()+1
			Rgrid = Rgrid[irb:ire]
		elif Xsteps!=None:
			Xgrid = Xgrid[-Xsteps:]

		coords = np.zeros((4,Xgrid.shape[0]*Rgrid.shape[0]*self.Num_p),order='F')
		RandPackO = np.asfortranarray(np.random.rand(Xgrid.shape[0],Rgrid.shape[0]))
		if 'FixedCell' in self.Configs:
			coords,Num_loc = chimera.genparts(coords,Xgrid,Rgrid,RandPackO,*self.Pax)
			coords = np.asfortranarray(coords[:,:Num_loc])
		elif 'RandCell' in self.Configs:
			xx, yy ,zz,wght = np.zeros(0),np.zeros(0),np.zeros(0),np.zeros(0)
			for ix in np.arange(Xgrid.shape[0]-1):
				for ir in np.arange(Rgrid.shape[0]-1):
					xx_cell = Xgrid[ix] + self.Args['dx']*\
					  (np.arange(self.Num_p)+0.5*np.random.rand(self.Num_p))/self.Num_p
					rr_cell = Rgrid[ir] + self.Args['dr']*\
					  (np.arange(self.Num_p)+0.5*np.random.rand(self.Num_p))/self.Num_p
					np.random.shuffle(xx_cell);np.random.shuffle(rr_cell);
					oo_cell = 2*np.pi*np.random.rand(self.Num_p)
					xx = np.r_[xx,xx_cell]
					yy = np.r_[yy, rr_cell*np.cos(oo_cell)]
					zz = np.r_[zz, rr_cell*np.sin(oo_cell)]
					rc = Rgrid[ir]+0.5*self.Args['dr']
					if Rgrid[ir]<0: rc = 0.125*self.Args['dr']
					wght = np.r_[wght,np.ones(self.Num_p)*rc]
					coords = np.asfortranarray(np.vstack((xx,yy,zz,wght)))
		Num_loc = coords.shape[1]

		if ProfileFunc == None:
			coords[-1] *= self.wght0
		elif len(getargspec(ProfileFunc).args)==1:
			coords[-1] *= self.wght0*ProfileFunc(coords[0])
		else:
			coords[-1] *= self.wght0*ProfileFunc(*coords[0:3])

		px = self.Configs['MomentaMeans'][0] + self.Configs['MomentaSpreads'][0]*np.random.randn(Num_loc)
		py = self.Configs['MomentaMeans'][1] + self.Configs['MomentaSpreads'][1]*np.random.randn(Num_loc)
		pz = self.Configs['MomentaMeans'][2] + self.Configs['MomentaSpreads'][2]*np.random.randn(Num_loc)
		g = np.sqrt(1. + px*px + py*py + pz*pz)
		new_parts = np.array(np.vstack(( coords[0:3], px,py,pz,g,coords[-1])),order='F')
		return new_parts

	def add_particles(self,new_parts):
		self.particles = np.concatenate((self.particles,new_parts),axis=1)
		self.particles_cntr = np.concatenate((self.particles_cntr,np.asfortranarray(new_parts[:3].copy()) ),axis=1)

	def make_field(self,i_step=0):
		if (self.particles.shape[1]==0) or ('Still' in self.Configs['Features']): return
		self.EB = np.zeros((6,self.particles.shape[1]),order='F')
		for device in self.Devices:
			pump_fld = device[0]
			self.EB = pump_fld(np.asfortranarray(self.particles[0:3]),self.EB,i_step*self.Configs['TimeStep'],*device[1:])

	def push_velocs(self,dt=None):
		if dt==None:dt=self.Configs['TimeStep']
		if self.particles.shape[1]==0 or ('Still' in self.Configs['Features']): return
		self.particles = chimera.push_velocs(self.particles,self.EB,self.push_fact*dt)

	def push_coords(self,dt=None):
		dt=self.Configs['TimeStep']
		if self.particles.shape[1]==0 or ('Still' in self.Configs['Features']): return
		self.particles, self.particles_cntr = chimera.push_coords(self.particles, self.particles_cntr,dt)

	def get_dens_on_grid(self,Nko=0):
		VGrid = 2*np.pi*self.Args['dx']*self.Args['dr']*self.Args['Rgrid']
		VGrid = (VGrid+(self.Args['Rgrid']==0))**-1*(self.Args['Rgrid']>0.0)
		dens = np.zeros((self.Args['Nx'],self.Args['Nr'],Nko+1),dtype='complex',order='F')
		dens = chimera.dep_dens(self.particles,dens,self.Args['leftX'],self.Args['Rgrid'],\
		  1./self.Args['dx'],1/self.Args['dr'])*VGrid[None,:,None]
		return dens

	def correct_fel(self,UdulLinCorrect = 0.001):
		self.particles[2] -= UdulLinCorrect
		self.particles_cntr[2] -= UdulLinCorrect

	def coxinel_line(self,transp = {'r11':10., 'r56':0.4e-3, 'lambda_u':2e-2, 'EE':180., 'lambda_r':200e-9,'foc':1.0}):
		self.particles, self.particles_cntr = cox_transport(self.particles,self.particles_cntr,transp)
		self.particles = np.asfortranarray(self.particles)
		self.particles_cntr = np.asfortranarray(self.particles_cntr)

	def denoise(self,WaveNums2Kill):
		for k_supp in WaveNums2Kill:
			particles_mirror = self.particles.copy()
			particles_mirror[0] = particles_mirror[0] + 0.5/k_supp
			self.particles = np.concatenate((self.particles,particles_mirror),axis=1)
			self.particles[-1,:] *= 0.5
			particles_mirror = self.particles_cntr.copy()
			particles_mirror[0] = particles_mirror[0] + 0.5/k_supp
			self.particles_cntr = np.concatenate((self.particles_cntr,particles_mirror),axis=1)

	def chunk_coords(self,position=None):
		if 'Xchunked' in self.Configs:
			if position=='cntr':
				chnk_ind,self.chunks,outleft,outright  = chimera.chunk_coords(self.particles_cntr,\
				  self.Args['Xgrid'],self.Configs['Xchunked'][0])
			else:
				chnk_ind,self.chunks,outleft,outright  = chimera.chunk_coords(self.particles,\
				  self.Args['Xgrid'],self.Configs['Xchunked'][0])
			if outright == 0:
				chnk_ind = chnk_ind.argsort()[outleft:]
			else:
				chnk_ind = chnk_ind.argsort()[outleft:-outright]
			if outleft!=0 or outright !=0: print('particles out', outleft,outright)

			self.particles, self.particles_cntr = \
			  chimera.align_coords(self.particles, self.particles_cntr,chnk_ind)
			self.particles = self.particles[:,:chnk_ind.shape[0]]
			self.particles_cntr = self.particles_cntr[:,:chnk_ind.shape[0]]
			self.EB = self.EB[:,:chnk_ind.shape[0]]

