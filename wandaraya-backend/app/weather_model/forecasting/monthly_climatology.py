import pandas as pd

class MonthlyClimatology:
    def predict(
            self,
            train:pd.DataFrame,
            test:pd.DataFrame,
    )->pd.DataFrame:
        """
        Predicts the monthly climatology for the test set based on the training data.

        Args:
            train (pd.DataFrame): Training data containing 'ds' (date) and 'y' (value).
            test (pd.DataFrame): Test data containing 'ds' (date)."""

        history=train[['ds','y']].copy()
        history['ds']=pd.to_datetime(history['ds'])
        history['y']=pd.to_numeric(history['y'],errors='coerce')
        history=history.dropna(subset=['y'])
        history['month']=history['ds'].dt.month
        monthly_means=history.groupby('month')['y'].mean().rename('yhat')

        result = test[["ds"]].copy()
        result["ds"] = pd.to_datetime(result["ds"])
        result["month"] = result["ds"].dt.month

        result = result.join(
            monthly_means,
            on="month",
        )

        return result[["ds", "yhat"]]
