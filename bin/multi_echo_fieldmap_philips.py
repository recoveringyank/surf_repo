#!/usr/bin/env python
import os,sys,argparse,re
import glob as gl
import subprocess as sp
import numpy as np
# import matplotlib.pyplot as plt
import nibabel as nib
from pathlib import Path
fsldir=os.getenv('FSLDIR')

### get arguments and parse them
parser = argparse.ArgumentParser(description='Generate phase image components of image from real and imaginary image components',usage='gen_phase.py -b < PAR file> > ',epilog=("Example usage: "+"gen_phase.py"),add_help=False)
if len(sys.argv) < 2:
	err="{cmd}"
	err=err.format(cmd=sys.argv[0])
	sp.call(["python",err,"--help"])
	sys.exit(1)

req_grp = parser.add_argument_group(title='Required arguments')
req_grp.add_argument('-b','--b0_seq',type=str,metavar='',required=True,help='Par Rec file')


#parser.add_argument('-a','--anat',type=str,metavar='',required=True,help='Anatomical Image aligned to mask space. Default is to sample images here for png output')
#parser.add_argument('-m','--mask',type=str,metavar='',required=True,help='Statistical or stat image to sample for output PNG file')
op_grp= parser.add_argument_group(title='Optional arguments')
op_grp.add_argument('-l','--alt',type=str,metavar='',help='Resample data to alternate reference image for slice represenation. Generally used in animal studies,args.alt')
op_grp.add_argument('-t','--thr',type=float,metavar='',help='Minimum threshold applied to statistical image. between 0-1. Default is 0.2')
op_grp.add_argument('-o','--out',type=str,metavar='',help='Specify output directory. Defualt is cwd/figures')
op_grp.add_argument("-h", "--help", action="help", help="show this help message and exit")
args=parser.parse_args()

#get those arguments into variables
b0=args.b0_seq


#parsing the par files to get rescale slope intercepts and echo times. 

meta="(re)scale"
with open(b0,"r") as par:
	for num,line in enumerate(par,1):
		if meta in line:
			idx=num
			print(idx)
data=[]
scinot = re.compile('[-+]?[\d]+\.?[\d]*[Ee](?:[-+]?[\d]+)?')
sci=[]
with open(b0,"r") as par:
	for num,line in enumerate(par):
		if num > idx:
			sci.append(re.findall(scinot,line))
			data.append(re.findall("[-+]?\d+\.\d+",line))
scale_slope=sci[1]
scale_slope=float(scale_slope[0])
data = [x for x in data if x != [] ]

for row in data:
	if float(row[0]) == 0:
		pass
	else:
		intercept=float((row[0]))
		rescale=float((row[1]))


print("slope intercept is {inter}".format(inter=intercept))
print(f'rescale slope is {rescale}')
print("slope scaling is {scale_slope}".format(scale_slope=scale_slope))


#### get the echo times 

echos="Max. number of echoes"
with open(b0,"r") as par:
	for num,line in enumerate(par,1):
		if echos in line:
			NE=re.findall('[0-9]+[0-9]',line)
			NE=int(NE[0])
print(f'Number of echos is {NE}')
echo_times=[]
for i in range(NE):
	echo_times.append(float(data[i][13]))
print(echo_times)

print("############# PAR/REC PARSING FINISHED #################")

print("############# CONVERTING TO NIFTI #################")
ruta=os.path.dirname(b0)
out=f'{ruta}/B0_fieldmap'
os.makedirs(out,exist_ok=True)
command=('/Applications/MRIcroGL/dcm2niix -o {out} -f %i ' ' -p n {b0}'.format(out=out,b0=b0))
print(command)
sp.run(command.split())


print('######## rescale the images #########')

print(NE)

os.chdir(out)
files=gl.glob('*gz')
start_real=NE+1
end_real=NE*2
start_imaginary=end_real+1
end_imaginary=NE * 3


magnitude=[files[i] for i in range(NE)]
real=[files[i] for i in range((start_real-1),end_real )]
imaginary=[files[i] for i in range((start_imaginary-1),end_imaginary)]

# ### time to rescale ##### 
# ### the magnitude images are fine with the dispaly value as is. However dcm2niix only picks up the intercept on the magnitude image which is zero. 
# ### here we correct the scaling on the real and imaginary components of the image by subtracting the intercept.  
# ### Philips uses the formula  DV = PV * RS + RI. As PV * RS is calculated the same because they share the RS we simply need to subtract the RI 

print(NE)
print(intercept)
for rl,im in zip(real,imaginary):
	print(rl,im)
	rlobj=nib.load(rl, mmap=False)
	rlhdr=rlobj.header
	rldat= rlobj.get_data().astype(float)
	rldat= np.add(rldat,intercept)

	rlobj= nib.nifti1.Nifti1Image(rldat, None, header=rlhdr)

	nib.save(rlobj,rl)

	imobj=nib.load(im, mmap=False)
	imhdr=imobj.header
	imdat= imobj.get_data().astype(float)
	imdat= np.add(imdat,intercept)

	imobj= nib.nifti1.Nifti1Image(imdat, None, header=imhdr)

	nib.save(imobj,im)

#### now that we have the corrected DV image for both the real and iamginary images we then calculate the floating point values for fieldmap generation 
#### here implemented as DV (iamges generated above) / RS * SS 
rs=rescale*scale_slope
for img in files:
	obj=nib.load(img,mmap=False)
	objhdr=obj.header
	objdat=obj.get_data().astype(float)

	objdat=np.divide(objdat,rs)

	obj=nib.nifti1.Nifti1Image(objdat, None, header=objhdr)

	nib.save(obj,img)

### congrats. the magnitude, real, and imaginary images are now all in the correct floating point range
### time to calculate phase via atan2 function and numpy. 
x=0
for rl,im in zip(real,imaginary):
	x=x+1
	X=str(x).zfill(4)
	out=f'phase_{X}.nii.gz'
	rlobj=nib.load(rl, mmap=False)
	rlhdr=rlobj.header
	rldat= rlobj.get_data().astype(float)

	imobj=nib.load(im, mmap=False)
	imhdr=imobj.header
	imdat= imobj.get_data().astype(float)
	
	geometry=imdat.shape

	im_vec=imdat.reshape(-1)
	rl_vec=rldat.reshape(-1)

	phase=np.arctan2(im_vec,rl_vec)
	phase=phase.reshape(geometry)

	phase_hdr=rlhdr.copy()
	phase_obj=nib.nifti1.Nifti1Image(phase, None, header=phase_hdr)
	nib.save(phase_obj,out)
print("######## PHASE IMAGES CALCULATED ############")
############### phase images calculated ############
phase_images=gl.glob('*phase*gz')
##### converting to radians
for  ph in phase_images:
	name=ph.split('.nii.gz')[0]
	out=f'{name}_rad.nii.gz'
	phase_obj=nib.load(ph,mmap=False)
	phase_hdr=phase_obj.header
	phase_dat=phase_obj.get_data().astype(float)
	geo=phase_dat.shape
	phase_vec=phase_dat.reshape(-1)
	phase_rad=(phase_vec + 2*np.pi)% (2*np.pi)
	phase_rad=phase_rad.reshape(geo)
	####save the phase radian image
	phase_rad_hdr=phase_hdr.copy()
	phase_rad_obj=nib.nifti1.Nifti1Image(phase_rad, None, header=phase_rad_hdr)
	nib.save(phase_rad_obj,out)
print("###### PHASE CONVERTED TO RADIANS#########")

## get brain mask. For animals change center variable 
final_mag=magnitude[-1]
center="63 63 7" #if huma... leave me blank. else use me 
out=final_mag.split('.nii.gz')[0]
betcmd="{fsldir}/bin/bet {final_mag} mag_brain -m -c {center} ".format(fsldir=fsldir,final_mag=final_mag,out=out,center=center)
sp.run(betcmd.split())

erocmd="{fsldir}/bin/fslmaths mag_brain_mask -ero mag_brain_mask".format(fsldir=fsldir)
sp.run(erocmd.split())
print("##### unwrapping phase images########")
phase_rads=gl.glob('*rad*gz')

print(sorted(phase_rads))

for  mag,phr in zip(magnitude,phase_rads):
	print(mag,phr)
	phase_uw=phr.split('.nii.gz')[0]
	uw=f'{phase_uw}_unwrapped'
	pre_cmd="{fsldir}/bin/prelude -a {mag} -p {phr} -o {uw} -m  mag_brain_mask  ".format(fsldir=fsldir,mag=mag,phr=phr,uw=uw) #optional -m  mag_brain_mask
	sp.run(pre_cmd.split())


########compute linear regression as performed by Windischberger et.al  DOI 10.102/jmri.20158	
## ###generate the deonminator
print("#####PERFORMING LINEAR REGRESSION #########")
echo_times=[x * 0.001 for x in echo_times]

dn1=[x**2 for x in echo_times]
dn1=sum(dn1)
dn2=sum(echo_times)**2
dn=dn1-dn2


### genrate the  numerator


UW=gl.glob('*unwrapped*gz')


fmap_geo=nib.load(UW[0],mmap=False)
fmap_hdr=fmap_geo.header

for i in range(len(UW)):
	UW[i]=nib.load(UW[i],mmap=False)
	UW[i]=UW[i].get_data().astype(float)

total_phase=sum(UW)
total_echo=sum(echo_times)
n2=np.multiply(total_phase,total_echo)

n1=[]
for ec,img in zip(echo_times,UW):
	n1.append(np.multiply(img,ec))
nn=sum(n1)-n2

fmap=np.divide(nn,dn)
fmap_obj=nib.nifti1.Nifti1Image(fmap,None,header=fmap_hdr)
nib.save(fmap_obj,'fieldmap.nii.gz')



#### fieldmap regularization #########

fg_cmg="fugue --loadfmap=fieldmap -m --savefmap=fieldmap_reg"
sp.run(fg_cmg.split())







