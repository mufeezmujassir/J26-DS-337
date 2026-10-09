import pandas as pd

class SeasonalNaiveBaseline:

    def predict(
            self,
            train: pd.DataFrame,
            test: pd.DataFrame,

    )->pd.DataFrame:

        history=train[["ds", "y"]].copy()
        future=test[["ds"]].copy()

        history["ds"] = pd.to_datetime(history["ds"])
        future["ds"] = pd.to_datetime(future["ds"])

        # Shift the historical dates forward by
        # exactly 12 calendar months.
        reference = history.copy()

        reference["ds"] = (
            reference["ds"]
            + pd.DateOffset(years=1)
        )

        reference = reference.rename(
            columns={"y": "yhat"}
        )

        result = future.merge(
            reference,
            on="ds",
            how="left",
            validate="one_to_one",
        )

        return result
