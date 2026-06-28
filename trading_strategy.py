import pandas as pd
import pandas_ta as ta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os

def backtest_strategy(ticker='SPY', use_mock=False):
    if use_mock:
        print("Usando datos de prueba (mock_data.csv)...")
        df = pd.read_csv('mock_data.csv')
    else:
        import yfinance as yf
        print(f"Descargando datos para {ticker}...")
        try:
            df = yf.download(ticker, start='2020-01-01', end='2023-12-31')
            if df.empty or 'Close' not in df.columns:
                print("Fallo en la descarga o datos vacíos. Usando mock data...")
                return backtest_strategy(ticker, use_mock=True)
        except Exception as e:
            print(f"Error al descargar: {e}. Usando mock data...")
            return backtest_strategy(ticker, use_mock=True)

    # Asegurarse de que Close sea una Serie de una sola columna si es MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Calcular indicadores
    df['SMA200'] = ta.sma(df['Close'], length=200)
    macd = ta.macd(df['Close'])
    df['MACD'] = macd['MACD_12_26_9']
    df['Signal'] = macd['MACDs_12_26_9']

    # Definir señales
    df['Buy_Signal'] = (df['MACD'] > df['Signal']) & (df['MACD'].shift(1) <= df['Signal'].shift(1)) & (df['Close'] > df['SMA200'])
    df['Sell_Signal'] = (df['MACD'] < df['Signal']) & (df['MACD'].shift(1) >= df['Signal'].shift(1))

    position = 0
    strategy_position = []
    for i in range(len(df)):
        if df['Buy_Signal'].iloc[i]:
            position = 1
        elif df['Sell_Signal'].iloc[i]:
            position = 0
        strategy_position.append(position)

    df['Strategy_Position'] = strategy_position

    # Calcular retornos
    df['Market_Returns'] = df['Close'].pct_change()
    df['Strategy_Returns'] = df['Market_Returns'] * df['Strategy_Position'].shift(1)

    df['Cumulative_Market'] = (1 + df['Market_Returns'].fillna(0)).cumprod()
    df['Cumulative_Strategy'] = (1 + df['Strategy_Returns'].fillna(0)).cumprod()

    # Métricas
    total_return = df['Cumulative_Strategy'].iloc[-1] - 1
    sharpe = (df['Strategy_Returns'].mean() / df['Strategy_Returns'].std()) * (252**0.5) if df['Strategy_Returns'].std() != 0 else 0

    print(f"\nResultados para {ticker}:")
    print(f"Retorno Total Estrategia: {total_return:.2%}")
    print(f"Retorno Total Mercado: {(df['Cumulative_Market'].iloc[-1]-1):.2%}")
    print(f"Sharpe Ratio: {sharpe:.2f}")

    # Graficar
    plt.figure(figsize=(12, 6))
    plt.plot(df['Cumulative_Market'], label='Mercado (Buy & Hold)')
    plt.plot(df['Cumulative_Strategy'], label='Estrategia (MACD + SMA200)')
    plt.title(f'Backtest: {ticker} - Estrategia vs Mercado')
    plt.legend()
    plt.savefig('performance.png')
    print("Gráfico guardado como performance.png")

if __name__ == "__main__":
    backtest_strategy('SPY')
