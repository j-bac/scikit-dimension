#
# BSD 3-Clause License
#
# Copyright (c) 2020, Jonathan Bac
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
import numpy as np
import warnings
from .._commonfuncs import get_nn, GlobalEstimator
from scipy.spatial.distance import pdist, squareform
from sklearn.utils.validation import check_array, check_is_fitted


class TLE(GlobalEstimator):
    """Intrinsic dimension estimation using the Tight Local intrinsic dimensionality Estimator algorithm.

    Attributes
    ----------
    epsilon : float
    

    References
    ----------

    Code translated from the original implementation by Miloš Radovanović (https://perun.pmf.uns.ac.rs/radovanovic/tle/).

    Laurent Amsaleg, Oussama Chelly, Michael E. Houle, Ken-ichi Kawarabayashi, Miloš Radovanović and Weeris Treeratanajaru. Intrinsic dimensionality estimation within tight localities. In Proceedings of the SIAM International Conference on Data Mining (SDM), pages 181–189, Calgary, Alberta, Canada, 2019
    """

    def __init__(self, k=20, epsilon=1e-4):
        self.k = k
        self.epsilon = epsilon

    def fit(self, X, y=None):
        """A reference implementation of a fitting function.
        Parameters
        ----------
        X : {array-like}, shape (n_samples, n_features)
            The training input samples.
        y : dummy parameter to respect the sklearn API

        Returns
        -------
        self : object
            Returns self.
        """
        X = check_array(X, ensure_min_samples=2, ensure_min_features=2)

        if self.k >= len(X):
            warnings.warn("k >= len(X), using k = len(X)-1")

        dists, inds = get_nn(X, min(self.k, len(X) - 1))

        self.dimension_ = np.zeros(len(X))
        for i in range(len(X)):
            self.dimension_[i] = self._idtle(X[inds[i, :]], dists[[i], :])

        self.is_fitted_ = True
        # `fit` should always return `self`
        return self

    def _idtle(self, nn, dists):
        # nn - matrix of nearest neighbors (k x d), sorted by distance
        # dists - nearest-neighbor distances (1 x k), sorted
        r = dists[0, -1]  # distance to k-th neighbor

        # Boundary case 1: If $r = 0$, this is fatal, since the neighborhood would be degenerate.
        if r == 0:
            raise ValueError("All k-NN distances are zero!")
        # Main computation
        k = dists.shape[1]
        V = squareform(pdist(nn))
        Di = np.tile(dists.T, (1, k))
        Dj = Di.T
        Z2 = 2 * Di ** 2 + 2 * Dj ** 2 - V ** 2
        S = (
            r
            * (
                ((Di ** 2 + V ** 2 - Dj ** 2) ** 2 + 4 * V ** 2 * (r ** 2 - Di ** 2))
                ** 0.5
                - (Di ** 2 + V ** 2 - Dj ** 2)
            )
            / (2 * (r ** 2 - Di ** 2))
        )
        T = (
            r
            * (
                ((Di ** 2 + Z2 - Dj ** 2) ** 2 + 4 * Z2 * (r ** 2 - Di ** 2)) ** 0.5
                - (Di ** 2 + Z2 - Dj ** 2)
            )
            / (2 * (r ** 2 - Di ** 2))
        )
        # handle case of repeating k-NN distances
        Dr = (dists == r).squeeze()
        S[Dr, :] = r * V[Dr, :] ** 2 / (r ** 2 + V[Dr, :] ** 2 - Dj[Dr, :] ** 2)
        T[Dr, :] = r * Z2[Dr, :] / (r ** 2 + Z2[Dr, :] - Dj[Dr, :] ** 2)
        # Boundary case 2: If $u_i = 0$, then for all $1\leq j\leq k$ the measurements $s_{ij}$ and $t_{ij}$ reduce to $u_j$.
        Di0 = (Di == 0).squeeze()
        T[Di0] = Dj[Di0]
        S[Di0] = Dj[Di0]
        # Boundary case 3: If $u_j = 0$, then for all $1\leq j\leq k$ the measurements $s_{ij}$ and $t_{ij}$ reduce to $\frac{r v_{ij}}{r + v_{ij}}$.
        Dj0 = (Dj == 0).squeeze()
        T[Dj0] = r * V[Dj0] / (r + V[Dj0])
        S[Dj0] = r * V[Dj0] / (r + V[Dj0])
        # Boundary case 4: If $v_{ij} = 0$, then the measurement $s_{ij}$ is zero and must be dropped. The measurement $t_{ij}$ should be dropped as well.
        V0 = (V == 0).squeeze()
        np.fill_diagonal(V0, False)
        # by setting to r, $t_{ij}$ will not contribute to the sum s1t
        T[V0] = r
        # by setting to r, $s_{ij}$ will not contribute to the sum s1s
        S[V0] = r
        # will subtract twice this number during ID computation below
        nV0 = np.sum(V0)
        # Drop T & S measurements below epsilon (V4: If $s_{ij}$ is thrown out, then for the sake of balance, $t_{ij}$ should be thrown out as well (or vice versa).)
        TSeps = (T < self.epsilon) | (S < self.epsilon)
        np.fill_diagonal(TSeps, 0)
        nTSeps = np.sum(TSeps)
        T[TSeps] = r
        T = np.log(T / r)
        S[TSeps] = r
        S = np.log(S / r)
        np.fill_diagonal(T, 0)  # delete diagonal elements
        np.fill_diagonal(S, 0)
        # Sum over the whole matrices
        s1t = np.sum(T)
        s1s = np.sum(S)
        # Drop distances below epsilon and compute sum
        Deps = dists < self.epsilon
        nDeps = np.sum(Deps, dtype=int)
        dists = dists[nDeps:]
        s2 = np.sum(np.log(dists / r))
        # Compute ID, subtracting numbers of dropped measurements
        ID = -2 * (k ** 2 - nTSeps - nDeps - nV0) / (s1t + s1s + 2 * s2)
        return ID
