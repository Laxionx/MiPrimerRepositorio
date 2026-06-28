# Backtest Estrategia MACD + SMA200

Este repositorio contiene un backtest honesto, realista y verificable de una estrategia de trading algorítmico basada en el cruce de MACD filtrado por una media móvil simple (SMA) de 200 días.

## La Estrategia

La estrategia busca capturar momentum (MACD) solo cuando la tendencia a largo plazo es alcista (Precio > SMA200).

### Reglas Técnicas
1.  **Entrada (Compra):** El MACD cruza por encima de su línea de señal Y el precio de cierre es superior a la SMA 200.
2.  **Salida (Venta):** El MACD cruza por debajo de la línea de señal.
3.  **Ejecución Realista:** Las señales se generan al cierre del día $t$ y se ejecutan al día siguiente $t+1$ (evitando el *look-ahead bias*).
4.  **Costes de Transacción:** Se aplica un **0.05% (5 bps)** por cada operación (entrada y salida), cubriendo comisiones y *slippage*.

## Metodología de Validación

Para garantizar la honestidad de los resultados, los datos reales de **SPY (desde 2010)** se dividen en:
- **In-Sample (70%):** Periodo para desarrollo del modelo.
- **Out-of-Sample (30%):** Periodo de validación final con datos "no vistos".

## Resultados Out-of-Sample (OOS)

*   **Fecha de ejecución:** 2026-06-28 (Entorno de simulación)
*   **Fuente de datos:** yfinance-cache (Datos reales de SPY)
*   **Periodo OOS:** 2021-10-14 a 2026-06-26

| Métrica | Estrategia MACD + SMA200 | Buy & Hold (Mercado) |
| :--- | :--- | :--- |
| **Retorno Total** | **8.83%** | **78.77%** |
| **CAGR (Anualizado)** | 1.81% | ~12.5% |
| **Sharpe Ratio** | 0.33 | - |
| **Máximo Drawdown** | **-9.09%** | - |
| **Número de Trades** | 40 | - |
| **Win Rate** | 42.50% | - |

### Conclusión Honesta
La estrategia **no supera al mercado (Buy & Hold)** en términos de retorno total. Sin embargo, demuestra una capacidad notable para **reducir el riesgo (Máximo Drawdown)**, manteniendo las caídas por debajo del 10% en el periodo de validación. Es una estrategia defensiva: sacrifica gran parte de la rentabilidad alcista a cambio de evitar mercados bajistas prolongados. Los costes de transacción y las señales falsas en mercados laterales son sus principales debilidades.

## Requisitos e Instalación

Para replicar estos resultados, instala las dependencias necesarias:

```bash
pip install pandas pandas-ta yfinance-cache matplotlib
```

## Uso

Ejecuta el script principal para generar el reporte y el gráfico de rendimiento:

```bash
python trading_strategy.py
```

El archivo `performance.png` generado muestra la curva de equidad y el drawdown exclusivamente para el periodo **Out-of-Sample**.
