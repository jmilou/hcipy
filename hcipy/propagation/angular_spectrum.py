import numpy as np
from .propagator import Propagator
from ..optics import Wavefront, make_agnostic_optical_element
from ..field import Field
from ..fourier import FastFourierTransform
from ..field import evaluate_supersampled, make_pupil_grid, subsample_field

@make_agnostic_optical_element()
class AngularSpectrumPropagator(Propagator):
	'''The monochromatic angular spectrum propagator for scalar fields.

	The scalar Angular Spectrum propagator is implemented as described by
	[1]_. The propagation of an electric field can be described as a transfer 
	function in frequency space. The transfer function is taken from 
	equation 9 of [1]_, and the related impulse response is taken from 
	equation 6 of [1]_.

	.. [1] Robert R. McLeod and Kelvin H. Wagner 2014, "Vector Fourier optics of anisotropic materials," Adv. Opt. Photon. 6, 368-412 (2014)

	Parameters
	----------
	input_grid : Grid
		The grid on which the incoming wavefront is defined.
	distance : scalar
		The distance to propagate
	num_oversampling : int
		The number of times the transfer function is oversampled. Default is 2.
	wavelength : scalar
		The wavelength of the wavefront.
	refractive_index : scalar
		The refractive index of the medium that the wavefront is propagating in.

	Raises
	------
	ValueError
		If the `input_grid` is not regular and Cartesian.
	'''
	def __init__(self, input_grid, distance, num_oversampling=2, wavelength=1, refractive_index=1):
		# The FFT requires a regular cartesian grid
		if not input_grid.is_regular or not input_grid.is_('cartesian'):
			raise ValueError('The input grid must be a regular, Cartesian grid.')
		
		self.fft = FastFourierTransform(input_grid, q=2)
		self.output_grid = input_grid

		k = 2 * np.pi / wavelength * refractive_index
		L_max = np.max(input_grid.dims * input_grid.delta)
		
		if np.any(input_grid.delta < wavelength * distance / L_max):			
			enlarged_input_grid = make_pupil_grid(2 * input_grid.dims, 2 * input_grid.delta * (input_grid.dims-1) )
			self.fft_up_scale = FastFourierTransform(enlarged_input_grid)

			def impulse_response_generator(grid):
				r_squared = grid.x**2 + grid.y**2 + distance**2
				r = np.sqrt(r_squared)
				cos_theta = distance / r
				return Field(cos_theta / (2 * np.pi) * np.exp(1j * k * r) * (1 / r_squared - 1j * k / r), grid)

			impulse_response = evaluate_supersampled(impulse_response_generator, enlarged_input_grid, num_oversampling)

			self.transfer_function = self.fft_up_scale.forward(impulse_response)

		else:
			def transfer_function_generator(grid):
				k_squared = grid.as_('polar').r**2
				k_z = np.sqrt(k**2 - k_squared + 0j)
				return Field(np.exp(1j * k_z * distance), grid)

			self.transfer_function = evaluate_supersampled(transfer_function_generator, self.fft.output_grid, num_oversampling)

	def forward(self, wavefront):
		'''Propagate a wavefront forward by a certain distance.
	
		Parameters
		----------
		wavefront : Wavefront
			The incoming wavefront.
		
		Returns
		-------
		Wavefront
			The wavefront after the propagation.
		'''
		ft = self.fft.forward(wavefront.electric_field)
		ft *= self.transfer_function
		return Wavefront(self.fft.backward(ft), wavefront.wavelength, wavefront.input_stokes_vector)
	
	def backward(self, wavefront):
		'''Propagate a wavefront backward by a certain distance.
	
		Parameters
		----------
		wavefront : Wavefront
			The incoming wavefront.
		
		Returns
		-------
		Wavefront
			The wavefront after the propagation.
		'''
		ft = self.fft.forward(wavefront.electric_field)
		ft *= np.conj(self.transfer_function)
		return Wavefront(self.fft.backward(ft), wavefront.wavelength, wavefront.input_stokes_vector)
