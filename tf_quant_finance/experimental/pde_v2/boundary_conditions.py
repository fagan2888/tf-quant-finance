# Lint as: python2, python3
"""Helper functions to construct boundary conditions of PDEs."""
import functools


def dirichlet(boundary_values_fn):
  """Wrapper for Dirichlet boundary conditions to be used in PDE solvers.

  Example: the boundary value is 1 on both boundaries.

  ```python
  def lower_boundary_fn(t, location_grid):
    return 1

  def upper_boundary_fn(t, location_grid):
    return 0

  solver = fd_solvers.step_back(...,
      boundary_conditions = [(dirichlet(lower_boundary_fn),
                              dirichlet(upper_boundary_fn))],
      ...)
  ```

  Also can be used as a decorator:

  ```python
  @dirichlet
  def lower_boundary_fn(t, location_grid):
    return 1

  @dirichlet
  def upper_boundary_fn(t, location_grid):
    return 0

  solver = fd_solvers.step_back(...,
      boundary_conditions = [(lower_boundary_fn, upper_boundary_fn)],
      ...)
  ```

  Args:
    boundary_values_fn: Callable returning the boundary values at given time.
      Can return a number, a zero-rank Tensor or a rank-one Tensor having the
      size of the batch. See pde_kernels.py for more details. Accepts one
       argument - the moment of time.

  Returns:
    Callable suitable for PDE solvers.
  """
  @functools.wraps(boundary_values_fn)
  def fn(t, x):
    # The boundary condition has the form alpha V + beta V_n = gamma, and we
    # should return a tuple (alpha, beta, gamma). In this case alpha = 1 and
    # beta = 0.
    return 1, None, boundary_values_fn(t, x)

  return fn


def neumann(boundary_normal_derivative_fn):
  """Wrapper for Neumann boundary condition to be used in PDE solvers.

  Example: the normal boundary derivative is 1 on both boundaries (i.e.
  `dV/dx = 1` on upper boundary, `dV/dx = -1` on lower boundary).

  ```python
  def lower_boundary_fn(t, location_grid):
    return 1

  def upper_boundary_fn(t, location_grid):
    return 0

  solver = fd_solvers.step_back(...,
      boundary_conditions = [(neumann(lower_boundary_fn),
                              neumann(upper_boundary_fn))],
      ...)
  ```

  Also can be used as a decorator:

  ```python
  @neumann
  def lower_boundary_fn(t, location_grid):
    return 1

  @neumann
  def upper_boundary_fn(t, location_grid):
    return 0

  solver = fd_solvers.step_back(...,
      boundary_conditions = [(lower_boundary_fn, upper_boundary_fn)],
      ...)
  ```

  Args:
    boundary_normal_derivative_fn: Callable returning the values of the
      derivative with respect to the exterior normal to the boundary at the
      given time.
      Can return a number, a zero-rank Tensor or a rank-one Tensor having the
      size of the batch. See pde_kernels.py for more details. Accepts one
      argument - the moment of time.

  Returns:
    Callable suitable for PDE solvers.
  """
  @functools.wraps(boundary_normal_derivative_fn)
  def fn(t, x):
    # The boundary condition has the form alpha V_n + beta V_n = gamma, and we
    # should return a tuple (alpha, beta, gamma). In this case alpha = 0 and
    # beta = 1.
    return None, 1, boundary_normal_derivative_fn(t, x)

  return fn
