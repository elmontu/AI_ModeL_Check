"""Small CPU convolutional classifier for bundled 8x8 digit images."""
import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.utils.validation import check_array, check_X_y, check_is_fitted
from sklearn.utils.multiclass import check_classification_targets

class TinyCNN(ClassifierMixin,BaseEstimator):
    def __init__(self,epochs=15,learning_rate=.03,random_state=3407):
        self.epochs=epochs;self.learning_rate=learning_rate;self.random_state=random_state
    def _patches(self,x):
        image=np.asarray(x).reshape(-1,8,8)
        return np.lib.stride_tricks.sliding_window_view(image,(3,3),axis=(1,2))
    def _forward(self,x):
        patches=self._patches(x)
        z=np.einsum('nhwij,kij->nhwk',patches,self.kernels_)+self.conv_bias_
        h=np.maximum(z,0).reshape(len(x),-1)
        logits=h@self.weights_+self.bias_
        logits-=logits.max(axis=1,keepdims=True)
        exp=np.exp(logits);p=exp/exp.sum(axis=1,keepdims=True)
        return patches,z,h,p
    def fit(self,x,y):
        x,y=check_X_y(x,y)
        check_classification_targets(y)
        if x.shape[1]!=64:raise ValueError('tiny CNN requires flattened 8x8 images')
        if not isinstance(self.epochs,(int,np.integer)) or self.epochs<1:raise ValueError('epochs must be a positive integer')
        if not np.isfinite(self.learning_rate) or self.learning_rate<=0:raise ValueError('learning_rate must be positive and finite')
        self.classes_,encoded=np.unique(y,return_inverse=True);self.n_features_in_=64
        rng=np.random.default_rng(self.random_state)
        self.kernels_=rng.normal(0,.12,(6,3,3));self.conv_bias_=np.zeros(6)
        self.weights_=rng.normal(0,.05,(216,len(self.classes_)));self.bias_=np.zeros(len(self.classes_))
        for _ in range(self.epochs):
            order=rng.permutation(len(x))
            for start in range(0,len(x),32):
                idx=order[start:start+32];patch,z,h,p=self._forward(x[idx]);p[np.arange(len(idx)),encoded[idx]]-=1;p/=len(idx)
                dh=(p@self.weights_.T).reshape(z.shape)*(z>0)
                dw=h.T@p;dk=np.einsum('nhwk,nhwij->kij',dh,patch)
                self.weights_-=self.learning_rate*np.clip(dw,-5,5)
                self.bias_-=self.learning_rate*p.sum(axis=0)
                self.kernels_-=self.learning_rate*np.clip(dk,-5,5)
                self.conv_bias_-=self.learning_rate*dh.sum(axis=(0,1,2))
        return self
    def predict_proba(self,x):
        check_is_fitted(self,'classes_')
        x=check_array(x)
        if x.shape[1]!=self.n_features_in_:raise ValueError('tiny CNN requires flattened 8x8 images')
        return self._forward(x)[-1]
    def predict(self,x):return self.classes_[self.predict_proba(x).argmax(axis=1)]
    @property
    def coefs_(self):return [self.kernels_,self.weights_]
    @property
    def intercepts_(self):return [self.conv_bias_,self.bias_]
