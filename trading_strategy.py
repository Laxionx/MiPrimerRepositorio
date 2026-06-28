import matplotlib
matplotlib.use('Agg')
import pandas as pd
import pandas_ta as ta
import matplotlib.pyplot as plt
import os
import yfinance_cache as yfc
from datetime import datetime
import sys

def get_real_data(ticker='SPY', start='2010-01-01'):
    """
    Obtiene datos históricos reales utilizando yfinance-cache como fuente robusta.
    """
    end = datetime.now().strftime('%Y-%m-%d')
    print(f"Intentando descargar datos reales para {ticker} desde {start} hasta {end}...")

    try:
        print("Usando yfinance-cache para mayor estabilidad...")
        dat = yfc.Ticker(ticker)
        df = dat.history(start=start, end=end)
        if not df.empty and 'Close' in df.columns:
            print("Datos descargados exitosamente.")
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df, "yfinance-cache"
    except Exception as e:
        print(f"Error al descargar datos: {e}")

    print("ERROR CRÍTICO: No se pudieron obtener datos reales de ninguna fuente.")
    print("El script debe abortar según los requisitos obligatorios.")
    sys.exit(1)

def calculate_metrics(df, returns_col, trades_count=None, win_rate=None):
    if df.empty:
        return {}

    cumulative = (1 + df[returns_col].fillna(0)).cumprod()
    total_return = cumulative.iloc[-1] - 1

    # Anualización (252 días de trading aprox)
    days = (df.index[-1] - df.index[0]).days
    years = days / 365.25
    cagr = (1 + total_return)**(1/years) - 1 if years > 0 and total_return > -1 else 0

    std = df[returns_col].std()
    sharpe = (df[returns_col].mean() / std) * (252**0.5) if std != 0 and not pd.isna(std) else 0

    peak = cumulative.cummax()
    drawdown = (cumulative - peak) / peak
    max_drawdown = drawdown.min()

    return {
        'Retorno Total': total_return,
        'CAGR': cagr,
        'Sharpe Ratio': sharpe,
        'Max Drawdown': max_drawdown,
        'Número de Trades': trades_count,
        'Win Rate': win_rate
    }

def get_trade_metrics(data, cost=0.0005):
    t_count = 0
    w_count = 0
    in_t = False
    t_ret = 1.0

    for j in range(1, len(data)):
        p_pos = data['Strategy_Position'].iloc[j-1]
        c_pos = data['Strategy_Position'].iloc[j]
        m_ret = data['Market_Returns'].iloc[j]

        if p_pos == 0 and c_pos == 1: # Entrada
            in_t = True
            t_ret = (1.0 - cost)
            t_count += 1
        elif p_pos == 1 and c_pos == 0: # Salida
            if in_t:
                t_ret *= (1 + m_ret)
                t_ret *= (1.0 - cost)
                if t_ret > 1.0: w_count += 1
                in_t = False
        elif in_t:
            t_ret *= (1 + m_ret)

    if in_t: # Cerrar trade ficticio al final para métricas
        t_ret *= (1.0 - cost)
        if t_ret > 1.0: w_count += 1

    w_rate = w_count / t_count if t_count > 0 else 0
    return t_count, w_rate

def backtest_strategy(ticker='SPY'):
    df_raw, source = get_real_data(ticker)
    df = df_raw.copy()

    # Cálculo de indicadores
    df['Market_Returns'] = df['Close'].pct_change()
    df['SMA200'] = ta.sma(df['Close'], length=200)
    macd = ta.macd(df['Close'])
    df['MACD'] = macd['MACD_12_26_9']
    df['Signal'] = macd['MACDs_12_26_9']

    # Reglas de la Estrategia
    df['Buy_Signal'] = (df['MACD'] > df['Signal']) & (df['MACD'].shift(1) <= df['Signal'].shift(1)) & (df['Close'] > df['SMA200'])
    df['Sell_Signal'] = (df['MACD'] < df['Signal']) & (df['MACD'].shift(1) >= df['Signal'].shift(1))

    # Limpiar datos
    df = df.dropna(subset=['SMA200', 'MACD', 'Signal', 'Market_Returns']).copy()

    # Lógica de posiciones
    position = 0
    strategy_position = []
    cost = 0.0005 # 0.05% por operación

    for i in range(len(df)):
        if df['Buy_Signal'].iloc[i]:
            position = 1
        elif df['Sell_Signal'].iloc[i]:
            position = 0
        strategy_position.append(position)

    df['Strategy_Position'] = strategy_position

    # Prevención de Look-ahead bias: la señal de t se ejecuta al precio de cierre de t+1
    # Por lo tanto, el retorno de t+1 se multiplica por la posición decidida al final de t.
    df['Strategy_Returns_Gross'] = df['Market_Returns'] * df['Strategy_Position'].shift(1)

    # Cálculo de costes (cada vez que la posición cambia de 0 a 1 o de 1 a 0)
    df['Position_Change'] = df['Strategy_Position'].diff().abs().fillna(0)
    if len(df) > 0 and df['Strategy_Position'].iloc[0] == 1:
        df.iloc[0, df.columns.get_loc('Position_Change')] = 1

    df['Trade_Costs'] = df['Position_Change'] * cost
    df['Strategy_Returns'] = df['Strategy_Returns_Gross'].fillna(0) - df['Trade_Costs']

    # División de datos: 70% In-Sample, 30% Out-of-Sample
    split_idx = int(len(df) * 0.7)
    df_is = df.iloc[:split_idx].copy()
    df_oos = df.iloc[split_idx:].copy()

    # Métricas In-Sample
    is_trades, is_win_rate = get_trade_metrics(df_is, cost)
    metrics_is = calculate_metrics(df_is, 'Strategy_Returns', is_trades, is_win_rate)
    bh_is = calculate_metrics(df_is, 'Market_Returns')

    # Métricas Out-of-Sample
    oos_trades, oos_win_rate = get_trade_metrics(df_oos, cost)
    metrics_oos = calculate_metrics(df_oos, 'Strategy_Returns', oos_trades, oos_win_rate)
    bh_oos = calculate_metrics(df_oos, 'Market_Returns')

    print(f"\n--- RESULTADOS DEL BACKTEST REAL ({ticker}) ---")
    print(f"Fuente de datos: {source}")
    print(f"Periodo Total Analizado: {df.index[0].date()} a {df.index[-1].date()}")

    print("\n[IN-SAMPLE (Entrenamiento/Optimización)]")
    for k, v in metrics_is.items():
        if v is not None:
            if any(x in k for x in ['Retorno', 'CAGR', 'Drawdown', 'Rate']):
                print(f"{k}: {v:.2%}")
            else:
                print(f"{k}: {v:.2f}")
    print(f"Retorno Buy & Hold: {bh_is['Retorno Total']:.2%}")

    print("\n[OUT-OF-SAMPLE (Validación Final)]")
    for k, v in metrics_oos.items():
        if v is not None:
            if any(x in k for x in ['Retorno', 'CAGR', 'Drawdown', 'Rate']):
                print(f"{k}: {v:.2%}")
            else:
                print(f"{k}: {v:.2f}")
    print(f"Retorno Buy & Hold: {bh_oos['Retorno Total']:.2%}")

    # Visualización Out-of-Sample
    df_oos['Cumulative_Strategy'] = (1 + df_oos['Strategy_Returns']).cumprod()
    df_oos['Cumulative_Market'] = (1 + df_oos['Market_Returns']).cumprod()

    plt.figure(figsize=(12, 10))

    # Curva de Equity
    ax1 = plt.subplot(2, 1, 1)
    ax1.plot(df_oos['Cumulative_Market'], label='Mercado (Buy & Hold)', color='gray', alpha=0.7)
    ax1.plot(df_oos['Cumulative_Strategy'], label='Estrategia (MACD + SMA200)', color='blue', linewidth=2)
    ax1.set_title(f'Rendimiento Out-of-Sample: {ticker}')
    ax1.set_ylabel('Valor Acumulado (Base 1.0)')
    ax1.legend()
    ax1.grid(True, linestyle='--', alpha=0.6)

    # Drawdown
    peak_oos = df_oos['Cumulative_Strategy'].cummax()
    drawdown_oos = (df_oos['Cumulative_Strategy'] - peak_oos) / peak_oos

    ax2 = plt.subplot(2, 1, 2, sharex=ax1)
    ax2.fill_between(drawdown_oos.index, drawdown_oos, 0, color='red', alpha=0.3)
    ax2.set_title('Drawdown de la Estrategia (OOS)')
    ax2.set_ylabel('Porcentaje de Caída')
    ax2.grid(True, linestyle='--', alpha=0.6)

    plt.tight_layout()
    plt.savefig('performance.png')
    print("\nGráfico de rendimiento OOS guardado como 'performance.png'")

    return metrics_oos, source, df.index[-1].date()

if __name__ == "__main__":
    backtest_strategy('SPY')
