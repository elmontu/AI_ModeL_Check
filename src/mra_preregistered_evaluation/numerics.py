"""Frozen zero-initialized ridge-logistic damped Newton solver.

The fitter boundary accepts public design and one route's decoded labels only.
It does not receive operator truth, retained responses, identifiers or future
labels. Every returned fit has an independent high-precision stationarity
certificate for the normative exact design/decoder, rather than a float-only
residual. No convergence fallback is available.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
import math
import numpy as np
from threadpoolctl import threadpool_limits

LAMBDA = 0.1
FLOAT_STOP = 5e-13
MAX_ITERATIONS = 256

class NumericalError(ValueError):
    pass


@dataclass(frozen=True)
class Fit:
    beta: np.ndarray
    iterations: int
    float_gradient_norm: float
    stationarity: dict

    def document(self):
        return {'coefficients':self.beta.tolist(),'iterations':self.iterations,'float_gradient_l2':self.float_gradient_norm,'stationarity':self.stationarity,'initialization':'exact_zero','lambda':'1/10','intercept_penalized':True}


def sigmoid(logits):
    z = np.asarray(logits,dtype=np.float64)
    p = np.empty_like(z)
    nonnegative = z >= 0
    p[nonnegative] = 1.0 / (1.0 + np.exp(-z[nonnegative]))
    e = np.exp(z[~nonnegative])
    p[~nonnegative] = e / (1.0 + e)
    return p


def chronological_sum(values, axis=0):
    values = np.asarray(values,dtype=np.float64)
    if values.shape[axis] == 0:
        raise NumericalError('Empty reduction refused')
    return np.take(np.add.accumulate(values,axis=axis),-1,axis=axis)


class _Design:
    """Sparse unbuffered chronological accumulation, or dense fixed-order path."""
    def __init__(self,X):
        self.X = X
        self.n,self.d = X.shape
        self.sparse = bool(self.d == 29 and np.all(X[:,0] == 1)
            and np.all((X[:,2:] == 0) | (X[:,2:] == 1))
            and np.all(np.sum(X[:,2:14],axis=1) == 1)
            and np.all(np.sum(X[:,14:],axis=1) == 1))
        if self.sparse:
            self.index = np.column_stack((np.zeros(self.n,dtype=np.int64),np.ones(self.n,dtype=np.int64),2+np.argmax(X[:,2:14],axis=1),14+np.argmax(X[:,14:],axis=1)))
            self.value = np.column_stack((np.ones(self.n),X[:,1],np.ones(self.n),np.ones(self.n)))
            self.hindex = (self.index[:,:,None]*self.d+self.index[:,None,:]).ravel()
            self.hvalue = (self.value[:,:,None]*self.value[:,None,:]).reshape(self.n,16)
        else:
            self.index = self.value = None

    def logits(self,beta):
        terms = self.value*beta[self.index] if self.sparse else self.X*beta[None,:]
        return chronological_sum(terms,axis=1)

    def objective_difference(self,beta,trial,v):
        """Stable float64 evaluation of the same frozen Armijo difference.

        softplus(z+d)-softplus(z)=log1p(sigmoid(z)*expm1(d)).
        The identity avoids cancellation of two absolute objectives near a
        stationary point. Large increments use stable logaddexp directly.
        This is always the Armijo arithmetic, not a convergence fallback.
        """
        change=trial-beta
        logits=self.logits(beta)
        delta=self.logits(change)
        difference=np.empty_like(logits)
        small=np.abs(delta)<=0.5
        difference[small]=np.log1p(sigmoid(logits[small])*np.expm1(delta[small]))
        difference[~small]=np.logaddexp(0.0,logits[~small]+delta[~small])-np.logaddexp(0.0,logits[~small])
        value=float(chronological_sum(difference-v*delta)/self.n
                    +0.05*chronological_sum(change*(2*beta+change)))
        return value

    def derivatives(self,beta,v,need_hessian=True):
        logits = self.logits(beta)
        p = sigmoid(logits)
        residual = p-v
        if self.sparse:
            g = np.zeros(self.d,dtype=np.float64)
            # add.at performs repeated-index additions unbuffered, in row-major
            # chronological order; each coordinate has the same ordered reduction.
            np.add.at(g,self.index.ravel(),(self.value*residual[:,None]).ravel())
            g = g/self.n+LAMBDA*beta
        else:
            g = chronological_sum(self.X*residual[:,None])/self.n+LAMBDA*beta
        objective = float(chronological_sum(np.logaddexp(0.0,logits)-v*logits)/self.n
                          +0.05*chronological_sum(beta*beta))
        if not need_hessian:
            return objective,g,None
        weights = p*(1-p)
        if self.sparse:
            H = np.zeros(self.d*self.d,dtype=np.float64)
            np.add.at(H,self.hindex,(self.hvalue*weights[:,None]).ravel())
            H = H.reshape(self.d,self.d)/self.n
        else:
            H = chronological_sum(self.X[:,:,None]*self.X[:,None,:]*weights[:,None,None])/self.n
        H[np.diag_indices(self.d)] += LAMBDA
        return objective,g,H


def objective_gradient_hessian(X,beta,targets):
    X=np.asarray(X,dtype=np.float64); beta=np.asarray(beta,dtype=np.float64); targets=np.asarray(targets,dtype=np.float64)
    return _Design(X).derivatives(beta,targets)


def fit_logistic(X, targets, *, exact_design=None, exact_targets=None):
    from .verifier import gradient_enclosure, prepare_exact_design
    X = np.asarray(X,dtype=np.float64)
    v = np.asarray(targets,dtype=np.float64)
    if (X.ndim != 2 or X.shape[1] != 29 or not 1 <= len(X) <= 65536
            or v.shape != (len(X),) or not np.isfinite(X).all() or not np.isfinite(v).all()):
        raise NumericalError('Only finite aligned 29-column public design and decoded targets admitted')
    prepared = prepare_exact_design(X, exact_design=exact_design)
    if prepared.norm_squared_upper > Decimal(4):
        raise NumericalError('Normative exact public design exceeds the registered R<=2 premise')
    design = _Design(X)
    beta = np.zeros(29,dtype=np.float64)
    with threadpool_limits(limits=1):
        for iteration in range(MAX_ITERATIONS+1):
            F,g,H = design.derivatives(beta,v)
            norm = math.sqrt(float(chronological_sum(g*g)))
            if not math.isfinite(F) or not np.isfinite(g).all() or not np.isfinite(H).all():
                raise NumericalError('Nonfinite solver state')
            if norm <= FLOAT_STOP:
                try:
                    stationarity = gradient_enclosure(X,beta,v,exact_design=prepared,exact_targets=exact_targets)
                except Exception as exc:
                    raise NumericalError(f'Independent true-gradient enclosure refused: {exc}') from exc
                if (stationarity.get('accepted') is not True or float(stationarity.get('norm_upper', math.inf)) > 1e-12
                        or float(stationarity.get('arithmetic_uncertainty_upper', math.inf)) > 5e-13):
                    raise NumericalError('Independent exact-gradient acceptance limits exceeded')
                beta.setflags(write=False)
                return Fit(beta,iteration,norm,stationarity)
            if iteration == MAX_ITERATIONS:
                raise NumericalError('Frozen Newton iteration cap reached')
            try:
                lower = np.linalg.cholesky(H)
                direction = np.linalg.solve(lower.T,np.linalg.solve(lower,-g))
            except np.linalg.LinAlgError as exc:
                raise NumericalError('Cholesky or triangular solve failed') from exc
            descent = float(chronological_sum(g*direction))
            if not np.isfinite(direction).all() or not descent < 0:
                raise NumericalError('Invalid Newton descent')
            step = 1.0
            accepted = False
            for halving in range(61):
                trial = beta+step*direction
                delta_objective = design.objective_difference(beta,trial,v)
                if math.isfinite(delta_objective) and delta_objective <= 0.0001*step*descent:
                    beta = trial
                    accepted = True
                    break
                if halving == 60:
                    break
                step *= 0.5
            if not accepted:
                raise NumericalError('Frozen Armijo 60-halving cap reached')
    raise NumericalError('Unreachable solver completion')


def predict_certified(X, fit, *, exact_design=None):
    from .verifier import certified_probabilities
    probabilities,certificate = certified_probabilities(X,fit.beta,exact_design=exact_design)
    if (np.asarray(probabilities).shape != (len(X),) or not np.isfinite(probabilities).all()
            or np.any(probabilities < 0) or np.any(probabilities > 1)):
        raise NumericalError('Certified prediction outside [0,1]')
    # The high-precision enclosure includes conversion to each delivered binary64
    # probability. This bound is consumed by the formal scoring error account.
    bound = certificate.get('maximum_absolute_error_upper',certificate.get('max_absolute_error_upper'))
    if bound is None or float(bound) > 1.2e-16:
        raise NumericalError('Probability conversion enclosure exceeds frozen arithmetic account')
    return probabilities,certificate


def brier_mean(probabilities,truth):
    p=np.asarray(probabilities,dtype=np.float64); y=np.asarray(truth,dtype=np.float64)
    if p.ndim != 1 or y.shape != p.shape or not np.all((y == 0) | (y == 1)) or np.any(p<0) or np.any(p>1):
        raise NumericalError('Bounded Brier inputs required')
    result=float(chronological_sum((p-y)*(p-y))/len(p))
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise NumericalError('Invalid Brier mean')
    return result


def arithmetic_error_account():
    """Worst-case absolute error, independent of empirical fit agreement.

    IEEE binary64 u=2^-53; a probability's certified absolute error <=1.2e-16.
    For frame n<=56, two subtractions/products per row and sequential sum/divide
    give <=2*e+e^2+gamma_64*(1+2*e+e^2). Pairing two frame losses doubles
    that bound; a gain subtraction contributes at most 2u. Sequential outer
    accumulation of N=16384 terms |gain|<=1 and division contributes <=2*gamma_(N+2), including division and rounding padding.
    Add the frozen strong-convexity two-fit optimization allowance 2e-11.
    Bounds concern primary Brier means/gains; descriptive cost grids have no
    inference or decision effect. Decimal interval proof certifies exp/logit
    arithmetic at every delivered prediction and exact-gradient acceptance.
    """
    from fractions import Fraction
    u=Fraction(1,2**53); e=Fraction(12,10**17)
    gamma=lambda k: k*u/(1-k*u)
    frame=2*e+e*e+gamma(64)*(1+2*e+e*e)
    arithmetic=2*frame+2*u+2*gamma(16386)
    solver=Fraction(2,10**11)
    total=solver+arithmetic
    if total > Fraction(1,10**9) or arithmetic > Fraction(98,10**11):
        raise NumericalError('Formal total gain error guard exceeded')
    rational=lambda q:f'{q.numerator}/{q.denominator}'
    return {'schema':'mra-phase7c-arithmetic-error-account/1.0','roundoff_unit':'1/9007199254740992','probability_absolute_error_cap':'3/25000000000000000','largest_scored_frame':56,'outer_trials':16384,'reduction_order':'chronological_sequential_float64','solver_gain_bound':'2/100000000000','scoring_and_accumulation_gain_bound':rational(arithmetic),'total_gain_bound':rational(total),'fixed_guard':'1/1000000000','within_fixed_guard':True,'formal_basis':'Directed Decimal enclosure for exact-gradient and delivered sigmoid; standard IEEE754 gamma_k absolute-error bound for bounded sequential arithmetic; lambda-strong convexity. Empirical independent agreement is separate qualification, not this proof.'}
