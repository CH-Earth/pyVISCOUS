import numpy as np
import pandas as pd
from   scipy.stats import multivariate_normal, norm, gaussian_kde
from   sklearn.cluster import KMeans
from   scipy.interpolate import interp1d     # used to estimate the empirical relationship between y_norm and y_cdf

import copulae
from   copulae import GaussianMixtureCopula  # used to apply GMCM more flexibly
from   copulae.core import pseudo_obs        # used to get data rank-based CDF
from   copulae.mixtures.gmc import GMCParam  # used to generate initial GMCM parameter estiamtes
from   copulae.mixtures.gmc.estimators.summary import FitSummary # used to get GMCM fitting results

def viscous(x, y, xIndex, sensType, N1=2000, N2=2000, n_components='optimal'):
    """ 
    Calculate the Sobol' first-order or total-order sensitivity indices based on the Gaussian Mixture Copula Model (GMCM).    
    
    Parameters
    -------
    x            : array, shape (n_samples, n_xvariables). x values in input space. 
    y            : array, shape (n_samples, 1). y values in output space. 
    xIndex       : int. The evaluated input variable index, starting from zero. 
                   e.g., Index 0 refers to the 1st input variable x1, meaning we aim to calculate the sensitivity index of x1.  
    sensType     : str. Type of Sensitivity index calculation. Two options: 'first', 'total'.
    N1           : int. Number of Monte Carlo samples used for the outer loop. Default N1=2000.
    N2           : int. Number of Monte Carlo samplesused for the inner loop. Default N2=2000. 
    n_components : integer or string "optimal". The number of components used in GMCM inference. Default n_components='optimal'.
                  If n_components is an integer, it will be used as the fixed user-provided number of components.
                  If n_components is "optimal", it will look for an optimal number of components in the range of [2, 9].
    
    Returns
    -------
    sens_indx    : scalar. Sobol' sensitivity index estimate.
    gmcm         : GMCM object. Best fitted GMCM. """
    
    # ################# Check arguments ################# 
    # Check if x or y is empty or full of the same value.
    if len(np.unique(x))<=1 or len(np.unique(x))<=1 or len(np.unique(y))<=1 or len(np.unique(y))<=1:
        print('Error: x or(and) y is empty or full of the same value.')
        return None
    
    # Check xIndex meets the requirement
    if not isinstance(xIndex, int):
        print('Error: Unrecognized xIndex. xIndex needs to be an integer.')
        return None
    
    # Check sensType meets the requirement
    if sensType in ['first', 'total']:
        print('Calculating %s-order sensitivity index for variable index %s...'%(sensType, xIndex))
    else:
        print('Error: Unrecognized sensType. sensType needs to be either "single" or "total"')
        return None

    # ################# PART A: Data preparation #################
    print('--- PART A: Data preparation')
    # Identify evaluated input-output data depending on sensType. 
    if sensType == 'first':
        x_sens = x[:,xIndex] # Select column(s) 
    elif sensType == 'total':               
        x_sens = np.delete(x, xIndex, axis=1) # Drop column(s) 
    
    # Reshape x_sens and y data. If shape(nSample,), reshape to (nSample,1).
    if len(np.shape(x_sens)) == 1: 
        x_sens = x_sens.reshape(-1,1) 
    if len(np.shape(y)) == 1: 
        y = y.reshape(-1,1) 

    # Normalize x_sens and y data
    # Note: Part B (GMCM inference) and Part C (Sensitivity index computation) are all based on normalized data.
    x_sens_norm = x_sens.copy()
    for ii in range(np.shape(x_sens)[1]):
        x_sens_norm[:,ii] = data_normalize(x_sens[:,ii])
    y_norm = data_normalize(y) 

    # Estimate y_norm variance. 
    varY = np.var(y_norm)

    # Interpolate the empirical relationship between y_norm and y_cdf for later use.   
    y_cdf = pseudo_obs(y_norm, ties='average') # Calclulate data rank-based CDF   
    cdf_y_function = interp1d(y_cdf.flatten(), y_norm.flatten(), fill_value=(min(y_norm), max(y_norm)), 
                              bounds_error=False, kind='linear', assume_sorted=False) 

    # ############### PARTS B & C ###################
    # Loop Parts B & C to avoid GMCM inference failure or sensitivity calculation failure, which is rare.
    trial_id  = 1 
    trial_max = 3

    while trial_id <= trial_max:

        print('--- PART B: GMCM inference')
        gmcm = gmcm_inference(x_sens_norm, y_norm, n_components=n_components)

        print('--- PART C: Sensitivity index computation')                    
        try:
            gmcm_params = getattr(gmcm, "params")  # Get gmcm params in case gmcm is null.
            sens_indx   = sensivitiy_index_estimation(sensType, gmcm, N1, N2, varY, cdf_y_function) # Compute sensitivity index.
        
        # Check if gmcm_inference succeeds.
        # If not, gmcm is null. No converged gmcm is obtained.
        except AttributeError: 
            trial_id = trial_id+1 
            print('    Warning: No convereged GMCM is obtained.')
            print('    Try another trial of Parts B & C.')
            continue 

        # Check if sensivitiy_index_estimation succeeds. 
        # If not, When sens_indx is nan due to the nan division issue.
        if np.isnan(sens_indx): 
            print('    Warning: sens_indx = NaN because zy_MarginalPDF has Nan or zero.')
            print('    Try another trial of Parts B & C.')
            trial_id = trial_id+1
            continue
        else: 
            # get a valid sensitivity result, exit the while loop.
            break          
        ############# END LOOP PARTS B & C  ###############
    
    # If there is no way to get a valid sensitivity result, output -999.
    # Possible reasons: insufficient samples, GMCM non-convergency.
    if not ('sens_indx' in locals()) or (np.isnan(sens_indx)):       
        print('    Warning: sens_indx = -999. Sensitivity calculation fails. Please check input-output data.')
        sens_indx = -999.0
        gmcm      = -999.0
        
    print('    Sensitivity index = %.6f'%(sens_indx))
    
    return sens_indx, gmcm

def data_normalize(data):
    """ 
    Normalize data using Min-Max Scalar.
    Normalization changes the data values to a common scale, without distorting differences in the ranges of values.
     
    Parameters
    -------
    data: array, shape (n, 1) or (n,). Input data.
    
    Returns
    -------
    z_data: array, shape is the sames as data. Normalized data."""    
        
    data_max = np.nanmax(data)
    data_min = np.nanmin(data)    
    z_data   = (data-data_min)/(data_max-data_min)    
    return z_data

        
def gmcm_inference(x_norm, y_norm, n_components='optimal'):
    """
    Gaussian Mixture Copula Model (GMCM) inference based on x_norm and y_norm. 

    Parameters
    ----------
    x_norm      : array, shape (n_samples, n_xvariables). X values in normalized space. 
    y_norm      : array, shape (n_samples, 1). Y values in normalized space. 
    n_components: integer or string "optimal". The number of components used in GMCM inference. 
                  If n_components is an integer, it will be used as the fixed user-provided number of components.
                  If n_components is "optimal", it will look for an optimal number of components in the range of [2,9].
                  Note 9 is hard coded to limit the number of parameters of GMCM.
        
    Returns
    -------
    Copulae fit_summary of the best fitted GMCM."""
    
    # PART B: GMCM inference    
    # ---------------------------------
    # Fit GMCM using different number of clusters.
    n_xvariables = np.shape(x_norm)[1]

    if isinstance(n_components, str) and n_components=='optimal':
        n_components = np.arange(2, 10) # Multiple candidate GMCMs. Hard coded to limit the number of parameters. 
    elif isinstance(n_components, int) and n_components>0:
        n_components = [n_components]
    else:
        print('The provided n_components does not meet the requirement: \
        a string "optimal" or an iteger greater than one.')

    # Combine x_norm and y_norm. Treat them as the multivariates of the Gaussian mixture model.
    data = np.concatenate((x_norm,y_norm), axis=1)

    # Fit GMCMs with different number of clusters.
    _, ndim = data.shape
    models = []
    bics = []
    aics=[]
    n_components_converg = []

    for n_component in n_components:
        print('    n_component = %d'%(n_component))
        
        # ---------------------------------
        # Fit a gmcm with n_component
        g_cop_gmcm = GaussianMixtureCopula(n_clusters=n_component, ndim=ndim)  

        # Use different initials to fit gmcm.
        trial_id  = 1
        trial_max = 3
        while trial_id <= trial_max:
            
            # Initialize gmcm params
            n_clusters, n_dim = int(n_component), int(n_xvariables+1)              
            if trial_id==1:
                try:
                    fit_summary = k_means(data, n_clusters, n_dim, ties='average',init='k-means++')
                except ValueError:
                    pass
            else:
                try:
                    fit_summary = k_means(data, n_clusters, n_dim,  ties='average',init='random')
                except ValueError:
                    pass
            
            # If fit_summary is obtained, pass it to param_init. Otherwise, move to the next trial.
            try:
                param_init = fit_summary.best_params
            except:
                print('\tinitial %d: fitting fails due to k_means initialization ValueError.'%(trial_id))
                trial_id = trial_id+1                
                continue

            # Fit gmcm params 
            try:
                g_cop_gmcm.fit(data, method='pem', x0=param_init, 
                               optim_options=None, ties='average', verbose=1, 
                               max_iter=10000, criteria='GMCM', eps=0.0001)  
                try:
                    # Get convegency label, convg_label
                    convg_label = getattr(g_cop_gmcm._fit_smry, "has_converged")
                    if convg_label:
                        print('\tinitial %d: fitting completes with convergency.'%(trial_id))
                        break
                    trial_id = trial_id+1
                except:
                    print('\tinitial %d: fitting completes until max iterations. Do not converge.'%(trial_id))
                    trial_id = trial_id+1                                        
                    continue
            except:
                print('\tinitial %d: fitting fails due to singular matrix error.'%(trial_id))
                trial_id = trial_id+1                
                continue                

        # ---------------------------------
        # Compute the AIC score for the fitted gmcm.  
        # Note: only record convereged gmcm.  
        try:
            # Get convegency label: convg_label
            convg_label = getattr(g_cop_gmcm._fit_smry, "has_converged")
           
            # Append the fitted gmcm to models
            models.append(g_cop_gmcm)
            
            # Calcualte BIC/AIC for the fitted gmcm 
            L = g_cop_gmcm._fit_smry.setup['Log. Likelihood']
            nsample = g_cop_gmcm._fit_smry.nsample
            nparam = n_component*ndim*ndim + n_component*ndim + n_component
#             bic = nparam*np.log(nsample) - 2*(L)
            aic = 2*nparam - 2*(L)
#             print('n_component=%d, log_like=%.2f, nparam=%d, aic=%.2f.'%(n_component, L, nparam, aic))

            n_components_converg.append(n_component)
#             bics.append(bic)        
            aics.append(aic) 
    
        except AttributeError:
            print("\tn_component=%d, do not converge."%(n_component))
            continue    
    # End n_components loops
    
    # ---------------------------------
    # Identify the best fitted gmcm.
    if n_components_converg: # if not empty.
        gmcm_model_comparisons = pd.DataFrame({"n_components" : n_components_converg, "AIC" : aics})

        # Identify the minimum BIC/AIC score corresponding index.
        best_model_index = gmcm_model_comparisons['AIC'].idxmin()

        # Identify the best fitted gmcm.
        best_model = models[best_model_index]
    else:
        best_model = []
        
    return best_model

def sensivitiy_index_estimation(sensType, gmcm, N1, N2, varY, cdf_y_function):
    """ 
    Compute the Sobol' sensitivity index using the fitted gmcm.
     
    Parameters
    -------
    sensType       : str. Type of Sensitivity index calculation. Two options: 'first', 'total'.
    gmcm           : Best fitted GMCM.
    N1             : int. Number of Monte Carlo samples used for the outer loop. Default N1=2000.
    N2             : int. Number of Monte Carlo samplesused for the inner loop. Default N2=2000. 
    varY           : scalar. The variance of y_norm.
    cdf_y_function : Empirical relationship between y_norm and y_cdf.
    
    Returns
    -------
    sens_indx      : scalar. Estiamted Sobol' sensitivity index."""    
        
    
    # PART C: Sensitivity index computation 
    # Two-loop-based Monte Carlo approximations of the first-order and the total-order sensitivity indices. 

    # --- Get gmcm params
    gmcm_params     = getattr(gmcm, "params")    
    gmcmWeights     = gmcm.params.prob       # shape (n_components,)
    gmcmMeans       = gmcm.params.means      # shape (n_components, n_variables). 
    gmcmCovariances = gmcm.params.covs       # (n_components, n_variables, n_variables).    
    gmcmNComponents = gmcm.params.n_clusters # number of components
    print('    Best GMCM n_component = ',gmcmNComponents)

    ################ OUTER LOOP ####################
    # OUTER LOOP: Loop N1 Monte Carlo samples to compute V(E(y│x_i)), variance of mean y conditioned on x_i. 

    # --- Generate N1 Monte Carlos multivariable samples based on the fitted GMCM (for the outer loop). 
    z1_MC_marginalCDF = gmcm.random(N1)                      # Return random gmcm marginal CDFs in range of [0,1]
    z1_MC = gmm_marginal_ppf(z1_MC_marginalCDF, gmcm.params) # Return the inverse values of gmcm marginal CDFs.

    # --- Generate empty arrays and flag.
    condEy   = np.zeros((N1,1))   # Store E(y│x_i), conditional expectation.
    condVarY = np.zeros((N1,1))   # Store E^2(y│x_i), conditional expectation square.
    flag     = 0                  # Flag for a division issue. 0: issue does not exist. 1: issue exists.

    # --- Loop N1 Monte Carlos samples.
    for r1 in range(N1):

        ################ INNER LOOP ####################
        # INNER LOOP: Loop N2 Monte Carlo samples to compute E(y│x_i), mean y conditioned on x_i. 
        # Note: The inner loop is realized using array operations.

        # --- Construct 2nd GMCM multivariable samples.
        z2_MC_marginalCDF = gmcm.random(N2) 
        z2_MC             = gmm_marginal_ppf(z2_MC_marginalCDF, gmcm.params)
        z2_MC[:,:-1]      = np.ones_like(z2_MC[:,:-1])*z1_MC[r1,:-1] # Replace x of z2_MC with x of the r1^th sample from z1_MC

        # Compute F^(-1)(zy2_MC), marginal CDF corresponding y values in observation space.
        y_MC = cdf_y_function(z2_MC_marginalCDF[:,-1]) # based on the interpolation relationship between y_norm and ycdf

        # --- Compute f(zy|zx)=f(zx,zy)/f(zx) based on GMCM.
        # Compute f(zx,zy), joint pdf of (zx,zy).
        xy_JointPDF = gmcm.pdf(z2_MC)  

        # Compute f(zx), marginal pdf of zx. 
        zx_MarginalPDFCpnt = [multivariate_normal.pdf(z1_MC[r1,:-1], mean=gmcmMeans[iComponent,:-1], 
                                                      cov=gmcmCovariances[iComponent,:-1,:-1]) for iComponent in range(gmcmNComponents)] 
        zx_MarginalPDF     = sum(zx_MarginalPDFCpnt*gmcmWeights) 

        # Compute f(zy|zx)=f(zx,zy)/f(zx), conditional pdf of zy.    
        zy_CondPDF         = np.divide(xy_JointPDF,zx_MarginalPDF)

        # --- Compute f(zy), marginal pdf of zy.
        zy_MarginalPDFCpnt = [multivariate_normal.pdf(z2_MC[:,-1], mean=gmcmMeans[iComponent,-1], 
                                                    cov=gmcmCovariances[iComponent,-1,-1]) for iComponent in range(gmcmNComponents)] 
        zy_MarginalPDF     = np.array(zy_MarginalPDFCpnt).transpose()@gmcmWeights 

        if np.isnan(zy_MarginalPDF).any() or (zy_MarginalPDF==0).any():
            flag = 1 # Division issue exists.
            break
        else:
            flag = 0 # Division issue does not exist.
            # --- Compute E(y|x), conditional expectation of y given zx_r1.
            r1_condEy        = sum(y_MC*zy_CondPDF/zy_MarginalPDF)/float(N2)  
            r1_condEy_sqaure = sum(y_MC*y_MC*zy_CondPDF/zy_MarginalPDF)/float(N2)  

            # --- Save E(y|x).   
            condEy[r1]   = r1_condEy
            condVarY[r1] = r1_condEy_sqaure - r1_condEy*r1_condEy

        ############## END INNER LOOP ###################
    
    if flag==1:   # Division issue exists.
        sens_indx = np.nan
    elif flag==0: # Division issue does not exist.
        
        # --- Compute Var(E(y|x)).
        varCondEy = np.var(condEy) 

        # --- Calculate E(Var(y|x)).
        meanCondVarY = np.mean(condVarY)                

        # --- Compute sensitivity index.   
        if sensType == 'first':
            sens_indx = varCondEy/varY         
        elif sensType == 'total':
            sens_indx = 1-varCondEy/varY     

    ################ END OUTER LOOP #################    
    
    return sens_indx

def k_means(data: np.ndarray, n_clusters: int, n_dim: int, ties='average', init='random'):
    """
    Determines the Gaussian Mixture Copula Model (GMCM) parameters via K-means.

    Parameters
    ----------
    data : np.ndarray. Input data.
    n_clusters : int. Number of clusters (components)
    n_dim : int. Number of dimension for each Gaussian distribution
    ties : { 'average', 'min', 'max', 'dense', 'ordinal' }, optional.
        Specifies how ranks should be computed if there are ties in any of the coordinate samples.
        This is effective only if the data has not been converted to its pseudo observations form.
    init: {‘random’,‘k-means++’}, default=’random’. 
        Method for initialization.

    Returns
    -------
    np.ndarray. Cumulative distribution function evaluated at `x` """

    data_cdf = pseudo_obs(data, ties)                        # get the data rank-based CDF
    km = KMeans(n_clusters, init=init,n_init='auto')         # initialize a K-mean function 
    km.fit(data_cdf)                                         # fit the K-mean function

    groups, prob = np.unique(km.labels_, return_counts=True)
    prob = prob / sum(prob)

    means = np.array([data[km.labels_ == g].mean(0) for g in groups])
    covs  = np.array([np.cov(data[km.labels_ == g], rowvar=False) for g in groups])

    return FitSummary(GMCParam(n_clusters, n_dim, prob, means, covs), True, 'kmeans', len(data_cdf),
                      {'Inertia': km.inertia_, 'ties': ties})

def gmm_marginal_ppf(u, param, resolution=2000, spread=5, validate=False):
    """
    Calculate the inverse cdf of the input u given the Gaussian Mixture Copula Model (GMCM) parameters.

    Parameters
    ----------
    u          : np.ndarray. Marginal CDF. Must be between [0, 1].
    param      : GMCParam. The Gaussian Mixture Copula parameters.
    resolution : int. The number of values used for approximation. 
                 The higher the resolution, the finer the interpolation.
                 However, it also comes at higher computation cost.
    spread     : int. The number of standard deviation to approximate the range of marginal probability.
    validate   : bool. If True, validates that all input marginal probability vector are between [0, 1] 
                 and raises an ValueError if condition isn't met.

    Returns
    -------
    ppf        : np.ndarray. Quantile corresponding to the lower tail probability u."""
    
    if validate and ((u < 0).any() or (u > 1).any()):
        raise ValueError("Invalid probability marginal values detected. Ensure that are values are between [0, 1]")

    # Number of samples for each cluster with a minimum of 2
    n_samples = np.maximum(np.round(param.prob * resolution), 2).astype(int)

    # Create evaluation grid
    grid = np.empty((n_samples.sum(), param.n_dim))
    i = 0
    for n, mu, sigma2 in zip(n_samples, param.means, param.covs):
        sigma = np.sqrt(np.diag(sigma2))
        grid[i:(i + n)] = np.linspace(mu - spread * sigma, mu + spread * sigma, n)
        i += n

    dist = gmm_marginal_cdf(grid, param)

    ppf = np.empty_like(u)
    for i in range(param.n_dim):
        # Do an inverse cdf, ppf, to get the marginals
        ppf[:, i] = interp1d(dist[:, i], grid[:, i], fill_value="extrapolate")(u[:, i]) # enable extrapolate.

    is_nan = np.isnan(ppf)
    if is_nan.any():
        ppf[is_nan & (u >= 1)] = np.inf   # infinity because marginal is greater or equal to 1
        ppf[is_nan & (u <= 0)] = -np.inf  # infinity because marginal is less than or equal to 0

    return ppf

def gmm_marginal_cdf(x, param):
    """
    Calculate the marginal cdf for the input x given the GMC parameters.

    Notes
    -----
    The approximation is taken from `Abramowitz and Stegun's Handbook of Mathematical
    Functions <http://people.math.sfu.ca/~cbm/aands/toc.htm>`_ formula 7.1.25.

    Parameters
    ----------
    x     : np.ndarray. Vector of quantiles
    param : GMCParam. The Gaussian Mixture Copula parameters

    Returns
    -------
    np.ndarray. Cumulative distribution function evaluated at `x` """

    sigmas = np.repeat(np.sqrt([np.diag(c) for c in param.covs]).T[np.newaxis, ...], len(x), axis=0)
    means = np.repeat(param.means.T[np.newaxis, ...], len(x), axis=0)

    a1 = 0.3480242
    a2 = -0.0958798
    a3 = 0.7478556
    rho = 0.47047
    sqrt2 = 1.4142136

    zi = (np.repeat(x[..., np.newaxis], param.n_clusters, axis=2) - means) / (sigmas * sqrt2)
    za = np.abs(zi)
    t = 1 / (1 + rho * za)
    erf = 0.5 * (a1 * t + a2 * t ** 2 + a3 * t ** 3) * np.exp(-(za ** 2))
    return np.where(zi < 0, erf, 1 - erf) @ param.prob
