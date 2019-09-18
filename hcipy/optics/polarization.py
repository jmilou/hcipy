import numpy as np
from .optical_element import OpticalElement, make_agnostic_optical_element
from ..field import Field, field_inv, field_dot, field_transpose, field_conjugate_transpose

def field_kron(a, b):
	'''Calculate the Kronecker product of two fields.

	Parameters
	----------
	a : tensor Field
		The first Field
	b : tensor Field
		The second Field

	Returns
	-------
	Field
		The resulting tensor field.
	'''
	is_a_field = hasattr(a, 'grid')
	is_b_field = hasattr(b, 'grid')

	is_output_field = is_a_field or is_b_field

	if not is_output_field:
		return np.kron(a, b)
	
	if is_a_field and is_b_field:
		if a.grid.size != b.grid.size:
			raise ValueError('Field sizes for a (%d) and b (%d) are not compatible.' % (a.grid.size, b.grid.size))
		grid = a.grid
	else:
		if is_a_field:
			grid = a.grid
		else:
			grid = b.grid

	if is_a_field:
		aa = a
	else:
		aa = a[..., np.newaxis]
	
	if is_b_field:
		bb = b
	else:
		bb = b[..., np.newaxis]
	
	output_tensor_shape = np.array(aa.shape[:-1]) * np.array(bb.shape[:-1])
	output_shape = np.concatenate((output_tensor_shape, [grid.size]))
	
	res = (aa[:, np.newaxis, :, np.newaxis, :] * bb[np.newaxis, :, np.newaxis, :, :]).reshape(output_shape)

	return Field(res, grid)

def jones_to_mueller(jones_matrix):
	'''Convert a Jones matrix to a Mueller matrix.

	Parameters
	----------
	jones_matrix : ndarray or tensor field
		The Jones matrix/matrices to convert to Mueller matrix/matrices.

	Returns
	-------
	ndarray or tensor Field
		The Mueller matrix/matrices.
	'''
	U = 1 / np.sqrt(2) * np.array([
		[1,  0,   0,  1],
		[1,  0,   0, -1],
		[0,  1,   1,  0],
		[0, 1j, -1j,  0]])
	
	return np.real(field_dot(U, field_dot(field_kron(jones_matrix, jones_matrix.conj()), U.conj().T)))

@make_agnostic_optical_element([], ['jones_matrix'])
class JonesMatrixOpticalElement(OpticalElement):
	'''A general Jones Matrix.

	Parameters
	----------
	jones_matrix : matrix or Field
		The Jones matrix describing the optical element. 

	'''
	def __init__(self, jones_matrix, wavelength=1):
		self.jones_matrix = jones_matrix

	def forward(self, wavefront):
		'''Propgate the wavefront through the Jones matrix.

		Parameters
		----------
		wavefront : Wavefront
			The wavefront to propagate.
		
		Returns
		-------
		Wavefront
			The propagated wavefront.
		'''
		wf = wavefront.copy()
		wf.electric_field = field_dot(self.jones_matrix, wf.electric_field)
		return wf
	
	def backward(self, wavefront):
		'''Propagate the wavefront backwards through the Jones matrix.

		Parameters
		----------
		wavefront : Wavefront
			The wavefront to propagate.
		
		Returns
		-------
		Wavefront
			The propagated wavefront.
		'''
		wf = wavefront.copy()
		wf.electric_field = field_dot(field_conjugate_transpose(self.jones_matrix), wf.electric_field)
		return wf

	def mueller_matrix(self):
		'''Returns the Mueller matrix of the Jones matrix. 
		'''
		return jones_to_mueller(self.jones_matrix)

	def __mul__(self, m):
		'''Multiply the Jones matrix on the right side with the Jones matrix m. 

		Parameters
		----------
		m : JonesMatrixOpticalElement, Field or matrix
			The Jones matrix with which to multiply. 
		'''
		if hasattr(m, 'jones_matrix'):
			return JonesMatrixOpticalElement(field_dot(self.jones_matrix, m.jones_matrix))
		else: 
			return JonesMatrixOpticalElement(field_dot(self.jones_matrix, m))

@make_agnostic_optical_element([], ['phase_retardation', 'fast_axis_orientation', 'circularity'])
class PhaseRetarder(JonesMatrixOpticalElement):
	'''A general phase retarder.

	Parameters
	----------
	phase_retardation : scalar or Field
		The relative phase retardation induced between the fast and slow axis.
	fast_axis_orientation : scalar or Field
		The angle of the fast axis with respect to the x-axis in radians.
	circularity : scalar or Field
		The circularity of the phase retarder.
	'''
	def __init__(self, phase_retardation, fast_axis_orientation, circularity, wavelength=1):
		phi_plus = np.exp(1j * phase_retardation / 2)
		phi_minus = np.exp(-1j * phase_retardation / 2)

		# calculating the individual components 
		j11 = phi_plus * np.cos(fast_axis_orientation)**2 + phi_minus * np.sin(fast_axis_orientation)**2
		j12 = (phi_plus - phi_minus) * np.exp(-1j * circularity) * np.cos(fast_axis_orientation) * np.sin(fast_axis_orientation)
		j21 = (phi_plus - phi_minus) * np.exp(1j * circularity) * np.cos(fast_axis_orientation) * np.sin(fast_axis_orientation)
		j22 = phi_plus * np.sin(fast_axis_orientation)**2 + phi_minus * np.cos(fast_axis_orientation)**2

		# constructing the Jones matrix. 
		jones_matrix = np.array([[j11, j12],[j21, j22]])

		# Testing if we can make it a Field. 
		if hasattr(j11, 'grid'):
			jones_matrix = Field(jones_matrix, j11.grid)

		JonesMatrixOpticalElement.__init__(self, jones_matrix, wavelength)

class LinearRetarder(PhaseRetarder):
	'''A general linear retarder.

	Parameters
	----------
	phase_retardation : scalar or Field
		The relative phase retardation induced between the fast and slow axis.
	fast_axis_orientation : scalar or Field
		The angle of the fast axis with respect to the x-axis in radians.
	'''
	def __init__(self, phase_retardation, fast_axis_orientation, wavelength=1):
		PhaseRetarder.__init__(self, phase_retardation, fast_axis_orientation, 0, wavelength)

class CircularRetarder(PhaseRetarder):
	'''A general circular retarder.
	
	Parameters
	----------
	phase_retardation : scalar or Field
		The relative phase retardation induced between the fast and slow axis.
	fast_axis_orientation : scalar or Field
		The angle of the fast axis with respect to the x-axis in radians.
	'''
	def __init__(self, phase_retardation, wavelength=1):
		PhaseRetarder.__init__(self, phase_retardation, np.pi / 4, np.pi / 2, wavelength)

class QuarterWavePlate(LinearRetarder):
	'''A quarter-wave plate.
	
	Parameters
	----------
	fast_axis_orientation : scalar or Field
		The angle of the fast axis with respect to the x-axis in radians.
	'''
	def __init__(self, fast_axis_orientation, wavelength=1):
		LinearRetarder.__init__(self, np.pi / 2, fast_axis_orientation, wavelength)

class HalfWavePlate(LinearRetarder):
	'''A half-wave plate.
	
	Parameters
	----------
	fast_axis_orientation : scalar or Field
		The angle of the fast axis with respect to the x-axis in radians.
	'''
	def __init__(self, fast_axis_orientation, wavelength=1):
		LinearRetarder.__init__(self, np.pi, fast_axis_orientation, wavelength)

class LinearPolarizer(JonesMatrixOpticalElement):
	'''A linear polarizer.

	Parameters
	----------
	polarization_angle : scalar or Field
		The polarization angle of the polarizer. Light with this angle is transmitted.
	'''
	def __init__(self, polarization_angle):
		self.polarization_angle = polarization_angle
	
	@property
	def polarization_angle(self):
		'''The angle of polarization of the linear polarizer.
		'''
		return self._polarization_angle
	
	@polarization_angle.setter
	def polarization_angle(self, polarization_angle):
		self._polarization_angle = polarization_angle

		c = np.cos(polarization_angle)
		s = np.sin(polarization_angle)
		self.jones_matrix = np.array([[c**2, -c * s],[-c * s, s**2]])
	
	def forward(self, wavefront):
		'''Propagate a wavefront forwards through the linear polarizer.

		Parameters
		----------
		wavefront : Wavefront
			The wavefront to propagate.
		
		Returns
		-------
		Wavefront
			The propagated wavefront.
		'''
		wf = wavefront.copy()
		wf.electric_field = field_dot(self.jones_matrix, wavefront.electric_field)
		return wf
	
	def backward(self, wavefront):
		'''Propagate a wavefront backwards through the linear polarizer.

		Parameters
		----------
		wavefront : Wavefront
			The wavefront to propagate.
		
		Returns
		-------
		Wavefront
			The propagated wavefront.
		'''
		return self.forward(wavefront)
 
#class PolarizingBeamSplitter(JonesMatrixOpticalElement):
''' A polarizing beam splitter that accepts one wavefront and returns two polarized wavefronts.
'''

#class RotatedJonesMatrixOpticalElement(JonesMatrixOpticalElement):
''' A rotated jones matrix.

Note: this rotates the polarization state, not the Field!

'''

#class Reflection(JonesMatrixOpticalElement):
''' A jones matrix that handles the flips in polarization for a reflection. + field flip around x- or y-axis 
'''

