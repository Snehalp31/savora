"""Leakage-aware chronological forecasting utilities."""
import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

def prepare_features(frame):
    df=frame.copy(); df['date']=pd.to_datetime(df['date']); df=df.sort_values(['product_id','location_id','date'])
    group=df.groupby(['product_id','location_id'],sort=False)['units_sold']
    for lag in (1,7,14): df[f'lag_{lag}']=group.shift(lag)
    df['rolling_mean_7']=df.groupby(['product_id','location_id'])['units_sold'].transform(lambda s:s.shift(1).rolling(7,min_periods=3).mean())
    df['day_of_week']=df['date'].dt.dayofweek; df['month']=df['date'].dt.month
    return df.dropna(subset=['lag_1','lag_7','lag_14','rolling_mean_7']).sort_values('date').reset_index(drop=True)

def evaluate_forecasters(frame):
    data=prepare_features(frame)
    if len(data)<60: return {'status':'insufficient_data','message':'At least 60 engineered rows are required; use the explicitly labelled historical-average baseline.','rows':len(data),'models':[]}
    features=['product_id','location_id','lag_1','lag_7','lag_14','rolling_mean_7','day_of_week','month']
    unique_dates=sorted(data['date'].unique()); cutoff=unique_dates[int(len(unique_dates)*.8)]
    train,test=data[data['date']<cutoff],data[data['date']>=cutoff]
    if train.empty or test.empty or train['date'].max()>=test['date'].min(): raise ValueError('Chronological split invalid')
    y=test['units_sold'].to_numpy(); group_means=train.groupby(['product_id','location_id'])['units_sold'].mean(); baseline=np.array([group_means.get((row.product_id,row.location_id),train['units_sold'].mean()) for row in test.itertuples()]); results=[]
    candidates=[('Historical-average baseline',None,baseline),('Random Forest',RandomForestRegressor(n_estimators=100,min_samples_leaf=3,random_state=42,n_jobs=-1),None),('Histogram Gradient Boosting',HistGradientBoostingRegressor(max_iter=100,l2_regularization=1,random_state=42),None)]
    for name,model,pred in candidates:
        if model is not None:
            model.fit(train[features],train['units_sold']); pred=np.maximum(0,model.predict(test[features]))
        results.append({'name':name,'mae':round(float(mean_absolute_error(y,pred)),3),'rmse':round(float(np.sqrt(mean_squared_error(y,pred))),3),'rows':len(test),'model':model})
    best=min(results,key=lambda r:r['mae'])
    trained_candidates=[r for r in results if r['model'] is not None]
    best_trained=min(trained_candidates,key=lambda r:r['mae']) if trained_candidates else None
    return {'status':'evaluated','features':features,'train_rows':len(train),'test_rows':len(test),'train_period':[train.date.min().date().isoformat(),train.date.max().date().isoformat()],'test_period':[test.date.min().date().isoformat(),test.date.max().date().isoformat()],'selected_model':best['name'],'trained_model':best_trained['name'] if best_trained else None,'models':[{k:v for k,v in r.items() if k!='model'} for r in results],'model_object':best_trained.get('model') if best_trained else None}
