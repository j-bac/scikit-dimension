import numpy as np
from scipy.optimize import minimize
from scipy.special import i0,i1,digamma
from sklearn.base import BaseEstimator
from sklearn.utils.validation import check_array
from _commonfuncs import randsphere, binom_coeff, get_nn

class DANCo(BaseEstimator):
    
    """ A template estimator to be used as a reference implementation.
    For more information regarding how to build your own estimator, read more
    in the :ref:`User Guide <user_guide>`.
    Parameters
    ----------
    demo_param : str, default='demo_param'
        A parameter used for demonstation of how to pass and store paramters.
    """
    def __init__(self,k=10,D=100,calibration_data=None,ver='DANCo'):
        self.k = k
        self.D = D
        self.calibration_data = calibration_data
        self.ver=ver

    def fit(self,X):
        """A reference implementation of a fitting function.
        Parameters
        ----------
        X : {array-like}, shape (n_samples, n_features)
            The training input samples.

        Returns
        -------
        self : object
            Returns self.
        """
        X = check_array(X, accept_sparse=False)
        self.estimated_dimension_, self.kl_divergence_, self.calibration_data_ = self._dancoDimEst(X)
        self.is_fitted_ = True
        # `fit` should always return `self`
        return self        
        
    def _KL(self,nocal, caldat):
        kld = self._KLd(nocal['dhat'], caldat['dhat'])
        klnutau = self._KLnutau(nocal['mu_nu'], caldat['mu_nu'],
                         nocal['mu_tau'], caldat['mu_tau'])
        #print(klnutau)
        return(kld + klnutau)

    def _KLd(self,dhat, dcal):
        H_k = np.sum(1/np.arange(1,self.k+1))    
        quo = dcal/dhat
        a = np.power(-1,np.arange(self.k+1))*np.array(list(binom_coeff(self.k,i) for i in range(self.k+1)))*digamma(1 + np.arange(self.k+1)/quo)
        return(H_k*quo - np.log(quo) - (self.k-1)*np.sum(a))

    def _KLnutau(self,nu1, nu2, tau1, tau2):
        return(np.log(i0(tau2)/i0(tau1)) + 
            i1(tau1)/i1(tau1)*(tau1 - tau2*np.cos(nu1-nu2)))

    def _get_nn(self,X,n_jobs=1):
        neigh = NearestNeighbors(n_neighbors=self.k,n_jobs=n_jobs)
        neigh.fit(X)
        dists, inds = neigh.kneighbors(return_distance=True)
        return dists,inds

    def _nlld(self, d, rhos, N):
        return(-self._lld(d, rhos, N))

    def _lld(self,d, rhos, N):
        if (d == 0):
            return(np.array([-1e30]))
        else:
            return N*np.log(self.k*d) + (d-1)*np.sum(np.log(rhos)) + (self.k-1)*np.sum(np.log(1-rhos**d))
        
    def _nlld_gr(self,d,rhos, N):
        if (d == 0):
            return(np.array([-1e30]))
        else:
            return -(N/d + np.sum(np.log(rhos) - (self.k-1)*(rhos**d)*np.log(rhos)/(1 - rhos**d)))

    def _MIND_MLk(self,rhos):
        N = len(rhos)
        d_lik = np.array([np.nan]*self.D)
        for d in range(self.D):
            d_lik[d] = self._lld(d, rhos, N)
        return(np.argmax(d_lik))

    def _MIND_MLi(self,rhos,dinit):
        res = minimize(fun=self._nlld,
                x0=np.array([dinit]),
                jac=self._nlld_gr,
                args=(rhos, len(rhos)),
                method = 'L-BFGS-B',
                bounds=[(0,self.D)])

        #if(!is.null(res$message)) print(res$message)
        return(res['x'])  


    def _MIND_MLx(self,X):
        nbh_data,idx = get_nn(X, self.k+1)
        rhos = nbh_data[:,0]/nbh_data[:,-1]

        d_MIND_MLk = self._MIND_MLk(rhos, self.k, self.D)
        if (self.ver == 'MIND_MLk'):
            return(d_MIND_MLk)

        d_MIND_MLi = self._MIND_MLi(rhos, self.k, self.D, d_MIND_MLk)
        if (self.ver == 'MIND_MLi'):
            return(d_MIND_MLi)
        else:
            raise ValueError("Unknown version: ", self.ver)

    @staticmethod
    def _Ainv(eta):
        if (eta < .53):
            return(2*eta + eta**3 + 5*(eta**5)/6)
        elif (eta < .85):
            return(-.4 + 1.39*eta + .43/(1-eta))
        else:
            return(1/((eta**3)-4*(eta**2)+3*eta))

    @staticmethod
    def _loc_angles(pt, nbs):
        vec = nbs-pt
       # if(len(pt) == 1):
       #     vec = vec.T
        vec_len = lens(vec)
        combs = indnComb(len(nbs), 2).T
        sc_prod = np.sum(vec[combs[0,:]]*vec[combs[1,:]],axis=1)
        #if (length(pt) == 1) {
        #print(sc.prod)
        #print((vec.len[combs[1, ]]*vec.len[combs[2, ]]))
        #}
        cos_th = sc_prod/(vec_len[combs[0,:]]*vec_len[combs[1,:]])
        if (any(abs(cos_th) > 1)):
            print(cos_th[np.abs(cos_th) > 1])
        return(np.arccos(cos_th))

    def _angles(self,X, nbs):
        N = len(X)
        self.k = nbs.shape[1]

        thetas = np.zeros((N, binom_coeff(self.k, 2)))
        for i in range(N):
            nb_data = X[nbs[i, ],]
            thetas[i, ] = self._loc_angles(X[i, ], nb_data)    
        return(thetas)

    def _ML_VM(self,thetas):
        sinth = np.sin(thetas)
        costh = np.cos(thetas)
        nu = np.arctan(np.sum(sinth)/np.sum(costh))
        eta = np.sqrt(np.mean(costh)**2 + np.mean(sinth)**2)
        tau = self._Ainv(eta)
        return dict(nu = nu, tau = tau)


    def _dancoDimEstNoCalibration(self,X):
        nbh_data,idx = get_nn(X, self.k+1)
        rhos = nbh_data[:,0]/nbh_data[:,-1]
        d_MIND_MLk = self._MIND_MLk(rhos)
        d_MIND_MLi = self._MIND_MLi(rhos, d_MIND_MLk)

        thetas = self._angles(X, idx[:,:self.k])
        ml_vm = list(map(self._ML_VM,thetas))
        mu_nu = np.mean([i['nu'] for i in ml_vm])
        mu_tau = np.mean([i['tau'] for i in ml_vm])
        if(X.shape[1] == 1):
            mu_tau = 1

        return dict(dhat = d_MIND_MLi, mu_nu = mu_nu, mu_tau = mu_tau)

    def _DancoCalibrationData(self, N):
        me = dict(k = self.k,
                N = N,
                calibration_data = list(),
                maxdim = 0)    
        return(me)

    def _increaseMaxDimByOne(self,dancoCalDat):
        newdim = dancoCalDat['maxdim'] + 1
        MIND_MLx_maxdim = newdim*2+5
        dancoCalDat['calibration_data'].append(self._dancoDimEstNoCalibration(randsphere(dancoCalDat['N'], newdim,1,center=[0]*newdim)[0]))
        dancoCalDat['maxdim'] = newdim
        return(dancoCalDat)

    def _computeDANCoCalibrationData(self,N):
        print('Computing calibration X...\nCurrent dimension: ',end=' ')
        cal=self._DancoCalibrationData(self.k,N)
        while (cal['maxdim'] < self.D):
            if cal['maxdim']%10==0:
                print(cal['maxdim'],end=' ')
            cal = self._increaseMaxDimByOne(cal)
        return cal


    def _dancoDimEst(self,X):

        cal = self.calibration_data
        N = len(X)

        if cal is not None:
            if (cal['k'] != self.k):
                raise ValueError("Neighborhood parameter self.k = %s does not agree with neighborhood parameter of calibration X, cal$self.k = %s",
                       self.k, cal['k'])
            if (cal['N'] != N):
                raise ValueError("Number of X points N = %s does not agree with number of X points of calibration X, cal$N = %s",
                       N, cal['N'])

        if (self.ver != 'DANCo'):
            return(self._MIND_MLx(X))

        nocal = self._dancoDimEstNoCalibration(X)
        if any(np.isnan(val) for val in nocal.values()):
            de=np.nan
            kl=np.nan
            return de, kl, cal

        if (cal is None):
            cal = self._DancoCalibrationData(N)

        if (cal['maxdim'] < self.D):
            print("Computing DANCo calibration X for N = {}, k = {} for dimensions {} to {}".format(N, self.k, cal['maxdim']+1, self.D))

        while (cal['maxdim'] < self.D):
            cal = self._increaseMaxDimByOne(cal)

        kl = np.array([np.nan]*self.D) 
        for d in range(self.D) :
            kl[d] = self._KL(nocal, cal['calibration_data'][d]) 

        de = np.argmin(kl)+1
        return de, kl[de-1], cal
