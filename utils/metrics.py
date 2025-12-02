"""
Statistical metrics for arbitrage analysis
"""

import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import adfuller
from typing import Tuple, Optional


def calculate_spread(price_a: float, price_b: float, mode: str = 'absolute') -> float:
    """
    Calculate price spread between two exchanges.
    
    Args:
        price_a: Price on exchange A
        price_b: Price on exchange B
        mode: 'absolute' for dollar difference, 'percentage' for % difference
    
    Returns:
        Spread value
    """
    spread = price_a - price_b
    
    if mode == 'percentage':
        return (spread / price_a) * 100 if price_a != 0 else 0
    
    return spread


def calculate_z_score(data: pd.Series, window: int = 20) -> pd.Series:
    """
    Calculate rolling Z-Score for time series data.
    
    Z-Score = (Current Value - Mean) / Standard Deviation
    
    Args:
        data: Pandas Series with spread values
        window: Rolling window size (default 20 periods)
    
    Returns:
        Pandas Series with Z-Score values
    """
    roll_mean = data.rolling(window=window).mean()
    roll_std = data.rolling(window=window).std()
    
    # Avoid division by zero
    z_score = (data - roll_mean) / roll_std.replace(0, np.nan)
    
    return z_score


def adf_test(series: pd.Series, significance_level: float = 0.05) -> Tuple[bool, float, dict]:
    """
    Perform Augmented Dickey-Fuller test for stationarity.
    
    The ADF test checks if a time series is stationary (mean-reverting).
    For arbitrage, we want the spread to be stationary.
    
    Args:
        series: Time series data (spread)
        significance_level: P-value threshold (default 0.05 = 95% confidence)
    
    Returns:
        Tuple of:
            - is_stationary: True if stationary (p-value < significance_level)
            - p_value: Statistical p-value
            - details: Dict with full test results
    """
    # Drop NaN values
    clean_series = series.dropna()
    
    if len(clean_series) < 10:
        return False, 1.0, {'error': 'Insufficient data for ADF test'}
    
    try:
        result = adfuller(clean_series, autolag='AIC')
        
        adf_statistic = result[0]
        p_value = result[1]
        used_lag = result[2]
        n_obs = result[3]
        critical_values = result[4]
        
        is_stationary = p_value < significance_level
        
        details = {
            'adf_statistic': adf_statistic,
            'p_value': p_value,
            'used_lag': used_lag,
            'n_observations': n_obs,
            'critical_values': critical_values,
            'is_stationary': is_stationary
        }
        
        return is_stationary, p_value, details
        
    except Exception as e:
        return False, 1.0, {'error': str(e)}


def calculate_spread_stats(spread_series: pd.Series) -> dict:
    """
    Calculate comprehensive statistics for a spread series.
    
    Args:
        spread_series: Pandas Series with spread values
    
    Returns:
        Dict with statistics
    """
    clean_data = spread_series.dropna()
    
    if len(clean_data) == 0:
        return {'error': 'No data available'}
    
    return {
        'mean': clean_data.mean(),
        'std': clean_data.std(),
        'min': clean_data.min(),
        'max': clean_data.max(),
        'current': clean_data.iloc[-1] if len(clean_data) > 0 else None,
        'median': clean_data.median(),
        'count': len(clean_data)
    }


def is_entry_signal(z_score: float, threshold: float = 2.0, 
                   spread_pct: Optional[float] = None, 
                   min_spread_pct: float = 0.0) -> Tuple[bool, str]:
    """
    Determine if current conditions signal an entry opportunity.
    
    Args:
        z_score: Current Z-Score value
        threshold: Z-Score threshold for entry (default 2.0)
        spread_pct: Current spread in percentage
        min_spread_pct: Minimum spread percentage to cover fees
    
    Returns:
        Tuple of (should_enter, reason)
    """
    if pd.isna(z_score):
        return False, "Z-Score is NaN"
    
    abs_z = abs(z_score)
    
    if abs_z < threshold:
        return False, f"Z-Score {abs_z:.2f} below threshold {threshold}"
    
    if spread_pct is not None and spread_pct < min_spread_pct:
        return False, f"Spread {spread_pct:.2%} below minimum {min_spread_pct:.2%}"
    
    direction = "SHORT A / LONG B" if z_score > 0 else "LONG A / SHORT B"
    return True, f"Entry signal: Z={z_score:.2f}, {direction}"


def is_exit_signal(z_score: float, exit_threshold: float = 0.5) -> Tuple[bool, str]:
    """
    Determine if current Z-Score signals position exit.
    
    Args:
        z_score: Current Z-Score value
        exit_threshold: Z-Score threshold for exit (default 0.5)
    
    Returns:
        Tuple of (should_exit, reason)
    """
    if pd.isna(z_score):
        return False, "Z-Score is NaN"
    
    abs_z = abs(z_score)
    
    if abs_z <= exit_threshold:
        return True, f"Exit signal: Z-Score converged to {z_score:.2f}"
    
    return False, f"Hold position: Z={z_score:.2f}"
