"""Explicitly labeled supervised ML. Synthetic training data is DEMO ONLY.

Outputs are decision-support signals, not definitive individual outcomes.
Historical outcome labels must refer to a *later* time than feature capture.
"""
import io
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, accuracy_score, precision_score, recall_score

FEATURES = ['marks_pct','attendance_pct','lms_pct','placement_pct','skills_pct','engagement_pct','backlog_count']

def vector(item):
    return [float(item[k]) if item.get(k) is not None else np.nan for k in FEATURES]

def synthetic_training(seed=42, n=1000):
    rng=np.random.default_rng(seed)
    marks=rng.uniform(35,98,n); attendance=rng.uniform(48,100,n)
    lms=rng.uniform(15,100,n); placement=rng.uniform(20,96,n)
    skills=rng.uniform(20,96,n); engagement=rng.uniform(10,100,n)
    backlog=rng.choice([0,1,2,3],size=n,p=[.62,.22,.12,.04])
    latent = (67-marks)*.072+(76-attendance)*.085+(50-lms)*.02+backlog*.8 + rng.normal(0,.8,n)
    prob=1/(1+np.exp(-np.clip(latent/2,-15,15)))
    y=rng.binomial(1,prob)
    X=np.column_stack([marks,attendance,lms,placement,skills,engagement,backlog])
    return X,y

def train(examples=None, demo=False):
    if demo: X,y=synthetic_training()
    else:
        if not examples or len(examples)<40:raise ValueError('At least 40 labeled historical examples are required.')
        X=np.array([vector(x['features']) for x in examples],dtype=float)
        y=np.array([int(x['outcome']) for x in examples],dtype=int)
    if len(set(y))<2 or min(np.bincount(y))<8:
        raise ValueError('Training needs at least 8 examples of both outcomes.')
    xtr,xt,ytr,yt=train_test_split(X,y,test_size=.25,random_state=42,stratify=y)
    model=make_pipeline(SimpleImputer(strategy='median',add_indicator=False,keep_empty_features=True),RandomForestClassifier(n_estimators=130,min_samples_leaf=5,max_depth=7,random_state=42,class_weight='balanced'))
    model.fit(xtr,ytr)
    prob=model.predict_proba(xt)[:,1]
    pred=(prob>=.5).astype(int)
    metrics={'roc_auc':round(float(roc_auc_score(yt,prob)),3),'accuracy':round(float(accuracy_score(yt,pred)),3),'precision':round(float(precision_score(yt,pred,zero_division=0)),3),'recall':round(float(recall_score(yt,pred,zero_division=0)),3),'test_count':len(yt),'train_count':len(ytr)}
    importance=sorted([{'feature':k,'importance':round(float(v),4)} for k,v in zip(FEATURES,model[-1].feature_importances_)],key=lambda a:-a['importance'])
    buf=io.BytesIO();joblib.dump(model,buf)
    return buf.getvalue(),{'source':'synthetic_demo' if demo else 'historical_labeled','metrics':metrics,'feature_importance':importance,'total_examples':len(y),'features':FEATURES}

def predict(blob,items):
    if not items:return []
    model=joblib.load(io.BytesIO(blob)) # only ever load artifacts created by this application's train()
    X=np.array([vector(x) for x in items],dtype=float)
    proba=model.predict_proba(X)[:,1]
    return [round(float(p),4) for p in proba]
