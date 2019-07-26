# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Lint as: python2, python3
"""Methods to approximate the implied vol of options from market prices."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import tensorflow as tf


def polya(option_prices,
          forwards,
          strikes,
          expiries,
          discount_factors=None,
          is_call_options=None,
          validate_args=False,
          polya_factor=(2 / np.pi),
          name=None):
  """Approximates the implied vol using the Stefanica-Radiocic algorithm.

  Finds an approximation to the implied vol using the Polya approximation for
  the Normal CDF. This algorithm was described by Stefanica and Radiocic in
  ref [1]. They show that if the Normal CDFs appearing in the Black Scholes
  formula for the option price are replaced with Polya's approximation, the
  implied vol can be solved for analytically. The Polya approximation produces
  absolute errors of less than 0.003 and the resulting implied vol is fairly
  close to the true value. For practical purposes, this may not be accurate
  enough so this result should be used as a starting point for a root finder.


  ## References:
  [1]: Dan Stefanica and Rados Radoicic. An explicit implied volatility formula.
    International Journal of Theoretical and Applied Finance,
    Vol. 20, no. 7, 2017.
    https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2908494
  [2]: Omar Eidous, Samar Al-Salman. One-term approximation for Normal
    distribution function. Mathematics and Statistics 4(1), 2016.
    http://www.hrpub.org/download/20160229/MS2-13405192.pdf

  Args:
    option_prices: A real `Tensor` of any shape. The prices of the options whose
      implied vol is to be calculated.
    forwards: A real `Tensor` of any shape. The current forward prices to
      expiry.
    strikes: A real `Tensor` of the same shape and dtype as `forwards`. The
      strikes of the options to be priced.
    expiries: A real `Tensor` of same shape and dtype as `forwards`. The expiry
      for each option. The units should be such that `expiry * volatility**2` is
      dimensionless.
    discount_factors: A real `Tensor` of same shape and dtype as the `forwards`.
      The discount factors to expiry (i.e. e^(-rT)). If not specified, no
      discounting is applied (i.e. the undiscounted option price is returned).
      Default value: None, interpreted as discount factors = 1.
    is_call_options: A boolean `Tensor` of a shape compatible with `forwards`.
      Indicates whether to compute the price of a call (if True) or a put (if
      False). If not supplied, it is assumed that every element is a call.
    validate_args: A Python bool. If True, indicates that arguments should be
      checked for correctness before performing the computation. The checks
      performed are: (1) Forwards and strikes are positive. (2) The prices
        satisfy the arbitrage bounds (i.e. for call options, checks the
        inequality `max(F-K, 0) <= Price <= F` and for put options, checks that
        `max(K-F, 0) <= Price <= K`.). (3) Checks that the prices are not too
        close to the bounds. It is numerically unstable to compute the implied
        vols from options too far in the money or out of the money.
      Default value: False
    polya_factor: A real scalar. The coefficient to use in the
      approximation for the Normal CDF. The approximation is: `N(x) ~ 0.5 + 0.5
        * sign(x) * sqrt[ 1 - exp(-k * x**2) ]` where `k` is the coefficient
        supplied with `polya_factor`. The original Polya approximation has the
        value `2 / pi` and this is approximation used in Ref [1]. However, as
        described in Ref [2], a slightly more accurate approximation is achieved
        if we use the value of `k=5/8`).
    name: (Optional) Python str. The name prefixed to the ops created by this
      function. If not supplied, the default name 'approx_implied_vol_polya' is
      used.
      Default value: None

  Returns:
    implied_vols: A `Tensor` of same shape and dtype as `option_prices`.
      The approximate implied total volatilities computed using the Polya
      approximation method.

  Raises:
    ValueError: If any of the prices do not satisfy the arbitrage bounds (i.e.
      for call options, if the inequality: `max(F-K, 0) <= Price <= F` is
      violated and an analogous constraint for puts.)
  """
  with tf.name_scope(name, 'approx_implied_vol_polya', [
      option_prices, forwards, strikes, expiries, discount_factors,
      is_call_options
  ]):
    option_prices = tf.convert_to_tensor(option_prices)
    dtype = option_prices.dtype
    forwards = tf.convert_to_tensor(forwards, dtype=dtype)
    strikes = tf.convert_to_tensor(strikes, dtype=dtype)
    expiries = tf.convert_to_tensor(expiries, dtype=dtype)
    if discount_factors is None:
      discount_factors = tf.convert_to_tensor(1.0, dtype=dtype)
    if is_call_options is not None:
      is_call_options = tf.convert_to_tensor(is_call_options)
    else:
      is_call_options = tf.ones_like(forwards, dtype=tf.bool)

    control_inputs = None
    if validate_args:
      control_inputs = _validate_args_control_deps(option_prices, forwards,
                                                   strikes, expiries,
                                                   discount_factors,
                                                   is_call_options)
    with tf.control_dependencies(control_inputs):
      adjusted_strikes = strikes * discount_factors
      normalized_prices = option_prices / adjusted_strikes
      normalized_forwards = forwards / strikes
      return _approx_implied_vol_polya(normalized_prices, normalized_forwards,
                                       expiries, is_call_options, polya_factor)


def _validate_args_control_deps(option_prices, forwards, strikes, expiries,
                                discount_factors, is_call_options):
  """Returns assertions for no-arbitrage conditions on the prices."""
  epsilon = tf.convert_to_tensor(1e-8, dtype=option_prices.dtype)
  forwards_positive = tf.debugging.assert_positive(forwards)
  strikes_positive = tf.debugging.assert_positive(strikes)
  expiries_positive = tf.debugging.assert_non_negative(expiries)
  put_lower_bounds = tf.nn.relu(strikes - forwards)
  call_lower_bounds = tf.nn.relu(forwards - strikes)
  lower_bounds = tf.where(
      is_call_options, x=call_lower_bounds, y=put_lower_bounds)
  upper_bounds = tf.where(is_call_options, x=forwards, y=strikes)
  undiscounted_prices = option_prices / discount_factors
  bounds_satisfied = [
      tf.debugging.assert_less_equal(lower_bounds, undiscounted_prices),
      tf.debugging.assert_greater_equal(upper_bounds, undiscounted_prices)
  ]
  not_too_close_to_bounds = [
      tf.debugging.assert_greater(
          tf.abs(undiscounted_prices - lower_bounds), epsilon),
      tf.debugging.assert_greater(
          tf.abs(undiscounted_prices - upper_bounds), epsilon)
  ]
  return [expiries_positive, forwards_positive, strikes_positive
         ] + bounds_satisfied + not_too_close_to_bounds


def _approx_implied_vol_polya(normalized_prices, normalized_forwards, expiries,
                              is_call_options, polya_factor):
  """Computes approximate implied vol using the Stefanica-Radoicic algorithm.

  ## Implementation Notes: The mapping between the notation used in the
  reference paper and the code below is as follows:
    y -> log_normalized_forwards
    alpha_c -> normalized_prices
  This notation is used in the in-line comments.

  Args:
    normalized_prices: `Tensor` of real dtype and any shape. The prices of the
      options to be inverted. Normalization means that the raw price is divided
      by the strike discounted to the present.
    normalized_forwards: `Tensor` or same dtype and shape as `normalized_prices`
      The forwards divided by the strike of the options.
    expiries: A real `Tensor` of same shape and dtype as `normalized_forwards`.
      The expiry for each option.
    is_call_options: Boolean `Tensor` of same shape as `normalized_prices` or
      None. Indicates whether a price is for a call option (if True) or a put
      option (if False). If None is specified, it is assumed that all the
      options are call options.
    polya_factor: Scalar `Tensor` of same dtype as `normalized_prices`. This is
      the factor to use for approximating the normal CDF in a Polya-like
      expression. Polya approximation is: N(x) ~ 0.5 + sign(x) sqrt(1-e^(-k
        x^2)) with k = 2 / pi. However, it has been found that other values for
        `k` may be more accurate. The value that minimizes the absolute error
        over the range [-10, 10] is 0.62305051 (approximately 5/8).

  Returns:
    implied_vols: A `Tensor` of same shape and dtype as
      `undiscounted_prices`. The approximate implied volatilities
      computed using the Polya approximation for the normal CDF.
  """
  if polya_factor is None:
    polya_factor = tf.convert_to_tensor(
        2.0 / np.pi, dtype=normalized_prices.dtype)
  ones = tf.ones_like(normalized_forwards)
  floored_forwards = tf.math.maximum(normalized_forwards, 1)
  capped_forwards = tf.math.minimum(normalized_forwards, 1)

  log_normalized_forwards = tf.math.log(normalized_forwards)
  sign_log_forward = tf.math.sign(log_normalized_forwards)

  if is_call_options is not None:
    option_signs = tf.where(is_call_options, ones, -ones)
  else:
    option_signs = 1
  signs = option_signs * sign_log_forward

  cdfs = 0.5 + 0.5 * signs * tf.math.sqrt(
      -tf.math.expm1(-2 * polya_factor * tf.math.abs(log_normalized_forwards)))

  # This corresponds to the expressions C_0 or P_0 in the table 2 of Ref [1].
  threshold = signs * (floored_forwards * cdfs - capped_forwards / 2)

  a, b, lnc = _get_quadratic_coeffs(normalized_prices, normalized_forwards,
                                    log_normalized_forwards, option_signs,
                                    polya_factor)
  c = tf.math.exp(lnc)
  lntwo = tf.convert_to_tensor(np.log(2.0), dtype=normalized_forwards.dtype)
  lnbeta = lntwo + lnc - tf.math.log(b + tf.math.sqrt(b * b + 4 * a * c))
  gamma = -lnbeta / polya_factor

  term1 = tf.math.sqrt(gamma + log_normalized_forwards)
  term2 = tf.math.sqrt(gamma - log_normalized_forwards)
  sqrt_var = tf.where(normalized_prices <= threshold,
                      sign_log_forward * (term1 - term2), term1 + term2)
  return sqrt_var / tf.math.sqrt(expiries)


def _get_quadratic_coeffs(normalized_prices, normalized_forwards,
                          log_normalized_forwards, option_signs, polya_factor):
  """Computes the coefficients of the quadratic in Stefanica-Radiocic method.

  Computes the coefficients described in Table 3 in Ref [1].

  Args:
    normalized_prices: `Tensor` of real dtype and any shape. The prices of the
      options to be inverted. Normalization means that the raw price is divided
      by the strike discounted to the present.
    normalized_forwards: `Tensor` or same dtype and shape as `normalized_prices`
      The forwards divided by the strike of the options.
    log_normalized_forwards: `Tensor` or same dtype and shape as
      `normalized_prices`. Log of the normalized forwards.
    option_signs: Real `Tensor` of same shape and dtype as `normalized_prices`.
      Should be +1 for a Call option and -1 for a put option.
    polya_factor: Scalar `Tensor` of same dtype as `normalized_prices`. This is
      the factor to use for approximating the normal CDF in a Polya-like
      expression. Polya approximation is (here `k` is the `polya_factor`) N(x) ~
      0.5 + sign(x) sqrt(1-e^(-k x^2)) with k = 2 / pi. However, it has been
      found that other values for `k` may be more accurate. The value that
      minimizes the absolute error over the range [-10, 10] is 0.62305051
      (approximately 5/8).

  Returns:
    (A, B, ln(C)): A 3-tuple of coefficients in terms of which the approximate
      implied vol is calculated.
  """
  # Corresponds to expressions in Table 3 in Ref [1].
  # corresponds to (e^y - 1) = F/K - 1
  q1 = normalized_forwards - 1
  # corresponds to (e^y + 1) = F/K + 1
  q2 = normalized_forwards + 1
  # r here corresponds to R in the paper and not to the interest rate.
  r = 2 * normalized_prices - option_signs * q1

  # f1 is e^{-polya_factor * y}, f2 is e^{polya_factor * y}
  f1 = tf.math.pow(normalized_forwards, -polya_factor)
  f2 = 1 / f1

  # g1 is e^{(1-polya_factor) y}, g2 is e^{-(1-polya_factor) y}
  g1 = f1 * normalized_forwards
  g2 = 1 / g1

  # a corresponds to the coefficient A in the paper.
  a = tf.math.square(g1 - g2)

  # b corresponds to the coefficient B in the paper.
  h = tf.math.square(normalized_forwards)
  r2 = tf.math.square(r)
  b = (4 * (f1 + f2) - 2 * (g1 + g2) * (1 + h - r2) / normalized_forwards)

  # lnc corresponds to the logarithm of C in the paper,
  # handled here on the log scale to minimize numerical instability.
  lnc1 = tf.math.log(4.0 * normalized_prices) + \
      tf.math.log(normalized_prices - option_signs * q1)
  lnc2 = tf.math.log(q2 - r) + tf.math.log(q2 + r)
  lnc = lnc1 + lnc2 - 2.0 * log_normalized_forwards

  return a, b, lnc